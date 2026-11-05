"""Benchmark reranker thật, tải model rõ ràng và không tự bật tính năng sau đo."""

import argparse
import json
import multiprocessing as mp
import os
import threading
import time
from pathlib import Path

import numpy as np
import psutil

from backend.core.config import ROOT, get_settings
from backend.rag.corpus import atomic_json
from backend.rag.snapshot import load_active_snapshot
from evaluation.evaluate_retrieval import CachedQueries, measure, prepare_cases


def download_worker(model_name: str, cache_dir: str, connection: object) -> None:
    """Dùng HTTP chuẩn của Hugging Face và trả lỗi gọn, không để tải model treo vô hạn."""
    os.environ["HF_HUB_DISABLE_XET"] = "1"
    os.environ["HF_HUB_DISABLE_PROGRESS_BARS"] = "1"
    try:
        from huggingface_hub import HfApi, snapshot_download

        info = HfApi().model_info(model_name)
        files = {item.rfilename for item in info.siblings}
        weight = "model.safetensors" if "model.safetensors" in files else "pytorch_model.bin"
        path = snapshot_download(
            model_name,
            revision=info.sha,
            cache_dir=cache_dir,
            max_workers=2,
            allow_patterns=[
                "config.json",
                "tokenizer*.json",
                "special_tokens_map.json",
                "sentencepiece.bpe.model",
                "vocab*",
                "merges.txt",
                weight,
            ],
        )
        connection.send({"path": path, "revision": info.sha})
    except (ImportError, OSError, ValueError, RuntimeError) as exc:
        connection.send({"error_type": type(exc).__name__})
    finally:
        connection.close()


def prepare_model(model_name: str, cache_dir: Path, timeout: float = 180) -> dict:
    """Giới hạn tổng thời gian tải bằng process có thể dừng, giữ cache đã tải được."""
    context = mp.get_context("spawn")
    parent, child = context.Pipe()
    process = context.Process(target=download_worker, args=(model_name, str(cache_dir), child))
    process.start()
    child.close()
    try:
        return parent.recv() if parent.poll(timeout) else {"error_type": "model_download_timeout"}
    except EOFError:
        return {"error_type": "model_download_process_failed"}
    finally:
        if process.is_alive():
            process.terminate()
        process.join(timeout=1)
        parent.close()


def benchmark(*, download: bool, output: Path) -> dict:
    """Đo CPU/RAM/latency và ablation trên corpus đã khóa; báo đúng lỗi tải model."""
    settings = get_settings()
    model_path = settings.reranker_model
    model_revision = None
    download_started = time.perf_counter()
    if download:
        downloaded = prepare_model(
            settings.reranker_model, settings.artifact_dir / "reranker_cache"
        )
        if "error_type" in downloaded:
            report = {
                "status": "model_unavailable",
                "model": settings.reranker_model,
                "error_type": downloaded["error_type"],
                "enabled_by_default": False,
            }
            atomic_json(output, report)
            return report
        model_path, model_revision = downloaded["path"], downloaded["revision"]
    snapshot = load_active_snapshot(settings)
    gold = json.loads((ROOT / "evaluation/retrieval_gold.json").read_text(encoding="utf-8"))
    cases = prepare_cases(gold, snapshot.rows)
    cache = CachedQueries(settings, ROOT / "artifacts/query_embeddings.json")
    measured_settings = settings.model_copy(
        update={
            "reranker_model": model_path,
            "reranker_timeout_seconds": 60,
            "enable_reranking": False,
        }
    )
    stop = threading.Event()
    samples = []

    def sample_memory() -> None:
        """Theo dõi cả process model con, không chỉ RAM process điều phối."""
        parent = psutil.Process(os.getpid())
        while not stop.is_set():
            total = parent.memory_info().rss
            for child in parent.children(recursive=True):
                try:
                    total += child.memory_info().rss
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    pass
            samples.append(total)
            stop.wait(0.05)

    sampler = threading.Thread(target=sample_memory, daemon=True)
    sampler.start()
    started = time.perf_counter()
    try:
        result = measure(
            measured_settings,
            cases,
            cache,
            modes=["vector_bm25_graph", "vector_bm25_graph_rerank"],
            base_store=snapshot.store,
        )
    finally:
        stop.set()
        sampler.join(timeout=1)
    report = result["reports"]["vector_bm25_graph_rerank"]
    base = result["reports"]["vector_bm25_graph"]
    applied = [r for r in report["results"] if r["trace"]["reranker"] == "applied"]
    warm = applied[1:] if len(applied) > 1 else []
    warm_p95 = float(np.percentile([r["latency_ms"] for r in warm], 95)) if warm else None
    total_ram = psutil.virtual_memory().total
    peak = max(samples) if samples else None
    heldout = report["by_split"]["heldout"]
    reference = base["by_split"]["heldout"]
    passed = bool(
        len(applied) == len(cases)
        and warm_p95 is not None
        and warm_p95 <= 5000
        and peak is not None
        and peak <= min(total_ram * 0.6, 8 * 1024**3)
        and heldout["recall_at_5"] >= reference["recall_at_5"]
        and heldout["mrr"] >= reference["mrr"]
    )
    summary = {
        "status": "completed",
        "model": settings.reranker_model,
        "model_revision": model_revision,
        "local_model_path": model_path,
        "download_ms": (started - download_started) * 1000,
        "benchmark_ms": (time.perf_counter() - started) * 1000,
        "cpu_threads": 2,
        "max_length": 384,
        "max_candidates": settings.reranker_max_candidates,
        "physical_ram_bytes": total_ram,
        "peak_parent_and_children_rss_bytes": peak,
        "warm_p95_ms": warm_p95,
        "applied_cases": len(applied),
        "total_cases": len(cases),
        "gate_passed": passed,
        "enabled_by_default": False,
        "gate_policy": "all calls applied; warm p95 <=5s; RSS <=min(60% RAM,8GiB); heldout Recall/MRR no worse than RRF",
        "results": result,
    }
    atomic_json(output, summary)
    return {k: v for k, v in summary.items() if k != "results"}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Benchmark model rerank local tùy chọn")
    parser.add_argument(
        "--download",
        action="store_true",
        help="Cho phép tải model công khai vào artifacts/reranker_cache",
    )
    parser.add_argument("--output", type=Path, default=ROOT / "artifacts/reranker_benchmark.json")
    args = parser.parse_args()
    print(
        json.dumps(
            benchmark(download=args.download, output=args.output), ensure_ascii=True, indent=2
        )
    )
