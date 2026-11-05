"""Đối chiếu kết quả Neo4j thật, chất lượng truy xuất và tính toàn vẹn baseline."""

import json
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone

import numpy as np

from backend.core.config import ROOT, get_settings
from backend.rag.corpus import atomic_json, collection_rows, fingerprint
from backend.rag.neo4j_connection import close_connections, get_connection
from backend.rag.snapshot import load_active_snapshot
from backend.rag.vector_store import VectorStore
from ingestion.migrate_neo4j import migrate_snapshot


def make_report() -> dict:
    """Không dùng metrics khác corpus, không coi unit test mock là database thật."""
    settings = get_settings()
    snapshot = load_active_snapshot(settings)
    repeated = migrate_snapshot(settings, snapshot.snapshot_id)
    baseline_dir = ROOT / "artifacts/baseline_niddk"
    baseline = json.loads((baseline_dir / "config.json").read_text(encoding="utf-8"))
    store = VectorStore(
        settings.model_copy(update={"chroma_collection": "diabetes_knowledge"}), create=False
    )
    data = store.collection.get(include=["embeddings"])
    order = sorted(range(len(data["ids"])), key=lambda index: data["ids"][index])
    actual = np.asarray(data["embeddings"], dtype=np.float32)[order]
    vectors_unchanged = np.array_equal(actual, np.load(baseline_dir / "embeddings.npy"))
    corpus_unchanged = fingerprint(collection_rows(store.collection)) == baseline["corpus_version"]
    if not vectors_unchanged or not corpus_unchanged:
        raise ValueError("Baseline corpus hoặc vector đã thay đổi; không xác nhận migration.")
    old = json.loads((ROOT / "artifacts/retrieval_ablation_niddk.json").read_text(encoding="utf-8"))
    parity = json.loads(
        (ROOT / "artifacts/retrieval_ablation_neo4j_rrf.json").read_text(encoding="utf-8")
    )
    guarded = json.loads(
        (ROOT / "artifacts/retrieval_ablation_neo4j_guarded.json").read_text(encoding="utf-8")
    )
    if any(
        report["corpus_version"] != snapshot.corpus_version for report in (old, parity, guarded)
    ):
        raise ValueError("Báo cáo retrieval khác corpus Neo4j hiện tại.")
    matched = sum(
        first["chunk_ids"] == second["chunk_ids"]
        for mode in old["reports"]
        for first, second in zip(
            old["reports"][mode]["results"], parity["reports"][mode]["results"], strict=True
        )
    )
    compared = sum(len(report["results"]) for report in old["reports"].values())
    if matched != compared:
        raise ValueError("Kết quả Neo4j chưa tương đương backend cũ.")
    base, graph = guarded["reports"]["vector"], guarded["reports"]["vector_graph"]
    passed = all(
        a[key] >= b[key]
        for a, b in [
            (graph, base),
            *[(graph["by_split"][s], base["by_split"][s]) for s in ("development", "heldout")],
        ]
        for key in ("recall_at_5", "mrr")
    )
    connection = get_connection(settings)
    server = connection.read(
        "CALL dbms.components() YIELD name, versions, edition RETURN name, versions, edition"
    )
    tests = ET.parse(ROOT / "artifacts/neo4j_test_results.xml").getroot().findall(".//testcase")
    successful = [
        test
        for test in tests
        if not any(test.find(tag) is not None for tag in ("failure", "error", "skipped"))
    ]
    neo_tests = [
        test
        for test in successful
        if test.attrib.get("classname", "").endswith("test_neo4j_integration")
    ]
    if len(successful) != len(tests) or not neo_tests:
        raise ValueError("Cần toàn bộ test đạt và có integration test Neo4j thật.")
    queries = [
        row
        for mode in ("vector_graph", "vector_bm25_graph")
        for row in guarded["reports"][mode]["results"]
        if row["trace"]["graph"].get("connected")
    ]
    no_failures = not any(
        row["trace"]["graph"].get("status") == "fallback"
        for mode in ("vector_graph", "vector_bm25_graph")
        for row in guarded["reports"][mode]["results"]
    )
    metrics = {
        mode: {
            key: report[key]
            for key in (
                "recall_at_5",
                "mrr",
                "ndcg_at_5",
                "latency_p95_ms",
                "by_split",
                "improved_cases",
                "regressed_cases",
                "graph_added_gold_evidence_cases",
            )
        }
        for mode, report in guarded["reports"].items()
    }
    return {
        "status": "verified",
        "checked_at": datetime.now(timezone(timedelta(hours=7))).isoformat(),
        "server": server,
        "python_driver": "6.4.0",
        "snapshot_id": snapshot.snapshot_id,
        "corpus_version": snapshot.corpus_version,
        "migration": repeated,
        "baseline_corpus_unchanged": corpus_unchanged,
        "baseline_vectors_unchanged": bool(vectors_unchanged),
        "networkx_neo4j_ranked_lists_matched": matched,
        "ranked_lists_compared": compared,
        "fusion_policy": "vector_guarded",
        "exploratory_quality_gate_passed": passed,
        "graph_request_cases_connected": len(queries),
        "ablation_no_graph_failures": no_failures,
        "query_embedding_requests_this_evaluation": guarded["query_embedding_requests"],
        "metrics": metrics,
        "tests": {
            "passed": len(successful),
            "real_neo4j_integration_passed": len(neo_tests),
            "failed_or_skipped": len(tests) - len(successful),
        },
        "runtime": {
            "graph_backend": settings.graph_backend,
            "graph_enabled": settings.enable_graph_retrieval,
            "bm25_enabled": settings.enable_hybrid_search,
            "reranker_enabled": settings.enable_reranking,
        },
        "a4_reranker": "Not rerun: prior real benchmark failed quality and latency gates.",
        "limitations": [
            "Exploratory agent-authored gold; not blinded or expert-reviewed.",
            "No new gold evidence beyond vector top-5 on this corpus.",
            "No end-to-end generation/groundedness measurement in this migration.",
            "Wikipedia remains blocked; no wiki documents imported.",
        ],
    }


if __name__ == "__main__":
    try:
        report = make_report()
        atomic_json(ROOT / "artifacts/neo4j_upgrade_report.json", report)
        print(
            json.dumps(
                {key: value for key, value in report.items() if key != "metrics"},
                ensure_ascii=True,
                indent=2,
            )
        )
    finally:
        close_connections()
