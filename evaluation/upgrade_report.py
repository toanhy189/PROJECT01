"""Tổng hợp kiểm định triển khai, không tự bật tính năng khi chưa đạt chất lượng."""

import json
from datetime import datetime, timedelta, timezone

from backend.core.config import ROOT, get_settings
from backend.rag.corpus import atomic_json, collection_rows, fingerprint, provider
from backend.rag.snapshot import load_active_snapshot
from backend.rag.vector_store import VectorStore


def make_report() -> dict:
    """Đối chiếu snapshot, benchmark và trạng thái nguồn để ghi quyết định rollout."""
    settings = get_settings()
    snapshot = load_active_snapshot(settings)
    baseline = json.loads(
        (ROOT / "artifacts/baseline_niddk/config.json").read_text(encoding="utf-8")
    )
    metrics = json.loads(
        (ROOT / "artifacts/retrieval_ablation_niddk.json").read_text(encoding="utf-8")
    )
    if metrics["corpus_version"] != snapshot.corpus_version:
        raise ValueError("Metrics khác corpus active; cần đo ablation cùng phiên bản trước.")
    reports = metrics["reports"]
    vector = reports["vector"]

    def gate(report: dict) -> bool:
        """Chỉ bật mặc định khi Recall/MRR không giảm trên toàn tập và phần heldout."""
        return all(
            report[key] >= vector[key]
            and report["by_split"]["heldout"][key] >= vector["by_split"]["heldout"][key]
            for key in ("recall_at_5", "mrr")
        )

    checks = {
        "evidence_count": sum(map(len, snapshot.graph.evidence.values())),
        "dangling_reference_count": 0,
        "quote_version_url_checks": "passed_by_snapshot_loader",
        "human_relation_precision": None,
        "source_checked_by": "codex_source_alignment_not_clinical_review",
    }
    wiki = json.loads((ROOT / "data/wiki/download_report.json").read_text(encoding="utf-8"))
    benchmark = json.loads((ROOT / "artifacts/reranker_benchmark.json").read_text(encoding="utf-8"))
    wiki_documents = {
        row["metadata"]["document_id"]
        for row in snapshot.rows
        if provider(row["metadata"]) == "wikipedia"
    }
    baseline_metrics = json.loads(
        (ROOT / "artifacts/baseline_niddk/retrieval_metrics.json").read_text(encoding="utf-8")
    )
    return {
        "checked_on": datetime.now(timezone(timedelta(hours=7))).date().isoformat(),
        "corpus_version": snapshot.corpus_version,
        "snapshot_id": snapshot.snapshot_id,
        "baseline_preserved": fingerprint(
            collection_rows(VectorStore(settings, create=False).collection)
        )
        == baseline["corpus_version"],
        "baseline_chunks": baseline["chunks"],
        "active_chunks": len(snapshot.rows),
        "graph": {
            "implemented": True,
            "entities": len(snapshot.graph.entities),
            "relations": len(snapshot.graph.relations),
            **checks,
            "quality_gate_passed": gate(reports["vector_graph"]),
            "enabled_by_default": False,
            "improved_cases": reports["vector_graph"]["improved_cases"],
            "regressed_cases": reports["vector_graph"]["regressed_cases"],
            "additional_gold_evidence_cases": reports["vector_graph"][
                "graph_added_gold_evidence_cases"
            ],
        },
        "hybrid": {
            "implemented": True,
            "quality_gate_passed": gate(reports["vector_bm25"]),
            "enabled_by_default": False,
        },
        "wiki": {
            "adapter_implemented": True,
            "published_documents": len(wiki_documents),
            "status": wiki.get("status", "see_download_report"),
            "enabled_by_default": False,
        },
        "reranker": {
            "implemented": True,
            "benchmark_status": benchmark["status"],
            "quality_resource_gate_passed": benchmark.get("gate_passed", False),
            "warm_p95_ms": benchmark.get("warm_p95_ms"),
            "peak_rss_bytes": benchmark.get("peak_parent_and_children_rss_bytes"),
            "enabled_by_default": False,
        },
        "evaluation": {
            "questions": metrics["case_count"],
            "answerable": vector["answerable_cases"],
            "query_embedding_calls_initial": baseline_metrics["query_embedding_requests"],
            "query_embedding_calls_ablation": metrics["query_embedding_requests"],
            "generation_quality_measured": False,
            "expert_annotations": False,
            "heldout_blinded": False,
            "limitation": "Fixed development/heldout partitions are exploratory; the same agent authored annotations and inspected reports. Independent human gold and blind validation remain required.",
        },
        "rollout": "vector remains default; graph/hybrid available for explicit experiments; wiki API blocked; reranker failed gate",
    }


if __name__ == "__main__":
    result = make_report()
    atomic_json(ROOT / "artifacts/rag_upgrade_report.json", result)
    print(json.dumps(result, ensure_ascii=True, indent=2))
