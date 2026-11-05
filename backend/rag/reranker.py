"""Reranker local nạp lười trong process riêng, có timeout và fallback RRF."""

import json
import multiprocessing as mp
import threading
import time
from pathlib import Path

import numpy as np

from backend.core.config import Settings
from backend.rag.models import Evidence


def reranker_worker(connection: object, model_name: str) -> None:
    """Chỉ đọc model đã cache; process phục vụ không tự tải thư viện/model từ mạng."""
    try:
        import torch
        from transformers import AutoModelForSequenceClassification, AutoTokenizer

        torch.set_num_threads(2)
        tokenizer = AutoTokenizer.from_pretrained(model_name, local_files_only=True)
        model = AutoModelForSequenceClassification.from_pretrained(
            model_name, local_files_only=True
        )
        model.to("cpu").eval()
        connection.send({"ready": True})
        while True:
            payload = connection.recv()
            if payload is None:
                break
            question, texts = payload
            scores = []
            with torch.inference_mode():
                for offset in range(0, len(texts), 4):
                    batch = texts[offset : offset + 4]
                    encoded = tokenizer(
                        [question] * len(batch),
                        batch,
                        padding=True,
                        truncation=True,
                        max_length=384,
                        return_tensors="pt",
                    )
                    values = model(**encoded).logits.reshape(-1).tolist()
                    scores.extend(values)
            connection.send({"scores": scores})
    except (ImportError, OSError, ValueError, RuntimeError, EOFError, BrokenPipeError):
        try:
            connection.send({"error": "reranker_unavailable"})
        except (BrokenPipeError, OSError):
            pass
    finally:
        connection.close()


class LocalReranker:
    """Giới hạn số ứng viên và thời gian thật bằng process có thể dừng."""

    def __init__(self, settings: Settings) -> None:
        """Không import transformers hoặc tạo process khi tính năng chưa được gọi."""
        self.settings = settings
        self.lock = threading.Lock()
        self.process = None
        self.connection = None
        self.retry_after = 0.0

    def close(self) -> None:
        """Dừng process lỗi/quá hạn và giải phóng pipe để không tích lũy tác vụ nền."""
        if self.process is not None:
            if self.process.is_alive():
                self.process.terminate()
            self.process.join(timeout=1)
        if self.connection is not None:
            self.connection.close()
        self.process = self.connection = None

    def rerank(self, question: str, candidates: list[Evidence]) -> tuple[list[Evidence], str]:
        """Nếu quá hạn/lỗi, giữ nguyên thứ tự RRF và báo trạng thái rõ ràng."""
        if not self.settings.enable_reranking or not candidates:
            return candidates, "disabled"
        deadline = time.monotonic() + self.settings.reranker_timeout_seconds
        if time.monotonic() < self.retry_after:
            return candidates, "fallback_cooldown"
        if not self.lock.acquire(timeout=self.settings.reranker_timeout_seconds):
            return candidates, "fallback_busy"
        try:
            if self.process is None or not self.process.is_alive():
                self.close()
                context = mp.get_context("spawn")
                self.connection, child = context.Pipe()
                model_name = self.settings.reranker_model
                report_path = self.settings.artifact_dir / "reranker_benchmark.json"
                if report_path.exists() and not Path(model_name).is_dir():
                    try:
                        report = json.loads(report_path.read_text(encoding="utf-8"))
                        cached = Path(report.get("local_model_path", "")).resolve()
                        cache_root = (self.settings.artifact_dir / "reranker_cache").resolve()
                        if (
                            report.get("model") == model_name
                            and cached.is_relative_to(cache_root)
                            and cached.is_dir()
                        ):
                            model_name = str(cached)
                    except (OSError, ValueError):
                        pass
                self.process = context.Process(
                    target=reranker_worker, args=(child, model_name), daemon=True
                )
                self.process.start()
                child.close()
                if not self.connection.poll(max(0, deadline - time.monotonic())):
                    raise TimeoutError
                if not self.connection.recv().get("ready"):
                    raise RuntimeError
            batch = candidates[: self.settings.reranker_max_candidates]
            self.connection.send((question, [item.text for item in batch]))
            if not self.connection.poll(max(0, deadline - time.monotonic())):
                raise TimeoutError
            scores = self.connection.recv().get("scores", [])
            if len(scores) != len(batch) or not np.isfinite(scores).all():
                raise ValueError
            reordered = [
                item
                for _, item in sorted(
                    zip(scores, batch),
                    key=lambda pair: (-float(pair[0]), pair[1].metadata["chunk_id"]),
                )
            ]
            return reordered + candidates[len(batch) :], "applied"
        except (TimeoutError, ValueError, RuntimeError, OSError, EOFError, BrokenPipeError):
            self.close()
            self.retry_after = time.monotonic() + 30
            return candidates, "fallback_timeout_or_unavailable"
        finally:
            self.lock.release()
