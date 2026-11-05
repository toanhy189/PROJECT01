"""Đo retrieval trên cùng corpus/query embedding, không gọi LLM sinh câu trả lời."""

import argparse
import json
import time
from pathlib import Path

import numpy as np

from backend.core.config import ROOT, Settings, get_settings
from backend.rag.corpus import atomic_json, collection_rows, fingerprint
from backend.rag.embedding_service import EmbeddingService
from backend.rag.retriever import Retriever
from backend.rag.vector_store import VectorStore


class CachedQueries:
    """Dùng lại embedding Gemini thật để so sánh thuật toán không bị nhiễu API."""

    def __init__(self, settings: Settings, path: Path) -> None:
        """Kiểm tra model/dimension và không tự tạo vector nếu thiếu dữ liệu."""
        self.settings, self.path = settings, path
        self.data = (
            json.loads(path.read_text(encoding="utf-8"))
            if path.exists()
            else {
                "embedding_model": settings.gemini_embedding_model,
                "embedding_dimension": settings.embedding_dimension,
                "vectors": {},
            }
        )
        if (
            self.data["embedding_model"] != settings.gemini_embedding_model
            or self.data["embedding_dimension"] != settings.embedding_dimension
        ):
            raise ValueError("Query cache không cùng cấu hình embedding.")

    def populate(self, questions: list[str]) -> int:
        """Gọi Gemini chỉ cho câu còn thiếu, ghi cache sau từng batch thành công."""
        missing = list(
            dict.fromkeys(q for q in questions if fingerprint(q) not in self.data["vectors"])
        )
        calls = 0
        service = EmbeddingService(self.settings)
        for offset in range(0, len(missing), 16):
            batch = missing[offset : offset + 16]
            values = service.embed(batch, query=True)
            calls += 1
            self.data["vectors"].update({fingerprint(q): v for q, v in zip(batch, values)})
            atomic_json(self.path, self.data)
        return calls

    def embed(self, texts: list[str], *, query: bool = False) -> list[list[float]]:
        """Chỉ trả embedding đã đo thật và kiểm tra kích thước/hữu hạn."""
        if not query:
            raise ValueError("Cache chỉ dùng cho query.")
        vectors = [self.data["vectors"][fingerprint(question)] for question in texts]
        array = np.asarray(vectors)
        if (
            array.shape != (len(texts), self.settings.embedding_dimension)
            or not np.isfinite(array).all()
            or not np.allclose(np.linalg.norm(array, axis=1), 1, atol=1e-4)
        ):
            raise ValueError("Query cache bị hỏng.")
        return vectors


def prepare_cases(gold: dict, rows: list[dict]) -> list[dict]:
    """Gán gold chunk theo quote nguồn, không chọn đáp án từ kết quả retrieval."""
    cases = []
    for item in gold["cases"]:
        groups = []
        for reference in item["references"]:
            relevant = [
                r["chunk_id"]
                for r in rows
                if r["metadata"]["document_id"] == reference["document_id"]
                and reference["quote"] in r["text"]
            ]
            if not relevant:
                raise ValueError(f"Gold quote không có trong corpus: {item['case_id']}")
            groups.append(relevant)
        cases.append(
            {
                **item,
                "relevant_groups": groups,
                "split": "development" if int(item["case_id"][1:]) % 3 == 0 else "heldout",
            }
        )
    return cases


def measure(
    settings: Settings,
    cases: list[dict],
    cache: CachedQueries,
    *,
    modes: list[str] | None = None,
    base_store: VectorStore | None = None,
) -> dict:
    """Ablation cùng corpus; groundedness/citation không đo bằng retrieval-only."""
    modes = modes or ["vector", "vector_bm25", "vector_graph", "vector_bm25_graph"]
    reports = {}
    for mode in modes:
        cfg = settings.model_copy(
            update={
                "enable_hybrid_search": "bm25" in mode,
                "enable_graph_retrieval": "graph" in mode,
                "enable_reranking": "rerank" in mode,
            }
        )
        # enable_wiki dùng để chọn corpus snapshot cho mọi mode, không chỉ mode graph.
        retriever = Retriever(cfg, cache, base_store)
        results = []
        for case in cases:
            started = time.perf_counter()
            found = retriever.retrieve_with_trace(case["question"])
            ids = [item.metadata["chunk_id"] for item in found.documents]
            relevant = {cid for group in case["relevant_groups"] for cid in group}
            recall = len(set(ids) & relevant) / len(relevant) if relevant else None
            rr = (
                next((1 / rank for rank, cid in enumerate(ids, 1) if cid in relevant), 0)
                if relevant
                else None
            )
            complete = (
                all(set(group) & set(ids) for group in case["relevant_groups"])
                if relevant
                else None
            )
            dcg = sum((1 / np.log2(rank + 1)) for rank, cid in enumerate(ids, 1) if cid in relevant)
            ideal = sum(
                1 / np.log2(rank + 1)
                for rank in range(1, min(len(relevant), settings.retrieval_k) + 1)
            )
            linked = {entity["entity_id"] for entity in found.trace["graph"]["linked_entities"]}
            expected = set(case.get("expected_entities", []))
            results.append(
                {
                    "case_id": case["case_id"],
                    "group": case["group"],
                    "split": case["split"],
                    "chunk_ids": ids,
                    "recall_at_5": recall,
                    "reciprocal_rank": rr,
                    "all_reference_groups_found": complete,
                    "ndcg_at_5": float(dcg / ideal) if ideal else None,
                    "entity_link_recall": len(linked & expected) / len(expected)
                    if expected and "graph" in mode
                    else None,
                    "entity_link_precision": len(linked & expected) / len(linked)
                    if expected and linked and "graph" in mode
                    else None,
                    "latency_ms": (time.perf_counter() - started) * 1000,
                    "trace": found.trace,
                }
            )
        answerable = [row for row in results if row["recall_at_5"] is not None]

        def aggregate(subset: list[dict]) -> dict:
            """Tổng hợp riêng development/heldout, không gán điểm cho câu không có gold."""
            values = [row for row in subset if row["recall_at_5"] is not None]
            return {
                "answerable_cases": len(values),
                "recall_at_5": float(np.mean([r["recall_at_5"] for r in values]))
                if values
                else None,
                "mrr": float(np.mean([r["reciprocal_rank"] for r in values])) if values else None,
                "ndcg_at_5": float(np.mean([r["ndcg_at_5"] for r in values])) if values else None,
                "all_reference_groups_found": sum(r["all_reference_groups_found"] for r in values),
            }

        reports[mode] = {
            **aggregate(answerable),
            "status": "completed"
            if not any(
                "snapshot_unavailable_using_vector" in r["trace"]["warnings"] for r in results
            )
            else "degraded",
            "entity_link_recall": float(
                np.mean(
                    [
                        r["entity_link_recall"]
                        for r in results
                        if r["entity_link_recall"] is not None
                    ]
                )
            )
            if any(r["entity_link_recall"] is not None for r in results)
            else None,
            "by_split": {
                split: aggregate([r for r in results if r["split"] == split])
                for split in ("development", "heldout")
            },
            "latency_mean_ms": float(np.mean([r["latency_ms"] for r in results])),
            "latency_p95_ms": float(np.percentile([r["latency_ms"] for r in results], 95)),
            "results": results,
        }
        if retriever.reranker is not None:
            retriever.reranker.close()
    baseline = {row["case_id"]: row for row in reports[modes[0]]["results"]}
    for mode, report in reports.items():
        useful, regressions, added = [], [], []
        for row in report["results"]:
            base = baseline[row["case_id"]]
            if row["recall_at_5"] is None:
                continue
            if (
                row["recall_at_5"] > base["recall_at_5"]
                or row["reciprocal_rank"] > base["reciprocal_rank"]
            ):
                useful.append(row["case_id"])
            if (
                row["recall_at_5"] < base["recall_at_5"]
                or row["reciprocal_rank"] < base["reciprocal_rank"]
            ):
                regressions.append(row["case_id"])
            case = next(c for c in cases if c["case_id"] == row["case_id"])
            relevant = {cid for group in case["relevant_groups"] for cid in group}
            graph_ids = {
                candidate["chunk_id"]
                for candidate in row["trace"].get("candidates", [])
                if "graph" in candidate["channels"]
            }
            if (set(row["chunk_ids"]) - set(base["chunk_ids"])) & relevant & graph_ids:
                added.append(row["case_id"])
        report["improved_cases"] = useful
        report["regressed_cases"] = regressions
        report["graph_added_gold_evidence_cases"] = added
    return {
        "evaluation_type": "retrieval_only_real_cached_gemini_queries",
        "k": settings.retrieval_k,
        "retrieval_policy_version": 3,
        "fusion_policy": settings.fusion_policy,
        "graph_backend": settings.graph_backend,
        "case_count": len(cases),
        "gold_annotation": "agent_source_checked_not_expert_reviewed",
        "citation_correctness": None,
        "groundedness_human": None,
        "unanswerable_note": "Candidates are not answers; refusals/groundedness require separate generation/Safety evaluation.",
        "reports": reports,
    }


def main() -> None:
    """Chạy baseline hoặc ablation; cache thiếu phải được yêu cầu bổ sung rõ ràng."""
    parser = argparse.ArgumentParser(description="Đánh giá retrieval không gọi LLM")
    parser.add_argument("--gold", type=Path, default=ROOT / "evaluation/retrieval_gold.json")
    parser.add_argument("--cache", type=Path, default=ROOT / "artifacts/query_embeddings.json")
    parser.add_argument("--populate-cache", action="store_true")
    parser.add_argument("--baseline-only", action="store_true")
    parser.add_argument("--rerank", action="store_true")
    parser.add_argument("--graph-backend", choices=["networkx", "neo4j"])
    parser.add_argument("--fusion-policy", choices=["rrf", "vector_guarded"])
    parser.add_argument("--output", type=Path, default=ROOT / "artifacts/retrieval_ablation.json")
    args = parser.parse_args()
    settings = get_settings()
    if args.graph_backend:
        settings = settings.model_copy(update={"graph_backend": args.graph_backend})
    if args.fusion_policy:
        settings = settings.model_copy(update={"fusion_policy": args.fusion_policy})
    cache = CachedQueries(settings, args.cache)
    gold = json.loads(args.gold.read_text(encoding="utf-8"))
    frozen = ROOT / "artifacts/baseline_niddk/retrieval_gold.json"
    if (
        args.gold.resolve() == (ROOT / "evaluation/retrieval_gold.json").resolve()
        and frozen.exists()
        and fingerprint(gold) != fingerprint(json.loads(frozen.read_text(encoding="utf-8")))
    ):
        raise ValueError("Gold set đã thay đổi so với baseline; cần tạo bộ đánh giá mới riêng.")
    calls = (
        cache.populate([item["question"] for item in gold["cases"]]) if args.populate_cache else 0
    )
    if args.baseline_only:
        settings = settings.model_copy(
            update={
                "enable_graph_retrieval": False,
                "enable_hybrid_search": False,
                "enable_wiki": False,
                "enable_reranking": False,
            }
        )
        store = VectorStore(settings, create=False)
        rows = collection_rows(store.collection)
        modes = ["vector"]
    else:
        from backend.rag.snapshot import load_active_snapshot

        snapshot = load_active_snapshot(settings)
        store, rows = snapshot.store, snapshot.rows
        modes = ["vector", "vector_bm25", "vector_graph", "vector_bm25_graph"]
        if args.rerank:
            modes.append("vector_bm25_graph_rerank")
    cases = prepare_cases(gold, rows)
    result = measure(settings, cases, cache, modes=modes, base_store=store)
    result.update(
        corpus_version=fingerprint(rows),
        embedding_model=settings.gemini_embedding_model,
        query_embedding_requests=calls,
        chunks=len(rows),
        gold_version=fingerprint(gold),
    )
    atomic_json(args.output, result)
    print(
        json.dumps(
            {
                **{k: v for k, v in result.items() if k != "reports"},
                "reports": {
                    name: {k: v for k, v in report.items() if k != "results"}
                    for name, report in result["reports"].items()
                },
            },
            ensure_ascii=True,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
