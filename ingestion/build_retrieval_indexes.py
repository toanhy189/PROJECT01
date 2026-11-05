"""Xây snapshot graph/BM25 từ Chroma hiện có mà không tạo lại embedding."""

import argparse
import json
from pathlib import Path

from backend.core.config import ROOT, Settings, get_settings
from backend.rag.corpus import atomic_json, collection_rows, fingerprint
from backend.rag.knowledge_graph import build_graph_data
from backend.rag.lexical import tokenize
from backend.rag.snapshot import file_hash, load_snapshot
from backend.rag.vector_store import VectorStore


def build_snapshot(
    settings: Settings,
    store: VectorStore,
    ontology: dict,
    annotations: list[dict],
    *,
    activate: bool = False,
) -> dict:
    """Kiểm tra toàn bộ bundle rồi mới đổi con trỏ active; giữ nguyên bản cũ khi lỗi."""
    rows = collection_rows(store.collection)
    graph = build_graph_data(rows, ontology, annotations)
    version = fingerprint(rows)
    identity = {
        "corpus_version": version,
        "graph_hash": fingerprint(graph),
        "embedding_model": settings.gemini_embedding_model,
        "embedding_dimension": settings.embedding_dimension,
        "collection": store.collection.name,
        "tokenizer_version": 1,
    }
    snapshot_id = fingerprint(identity)
    directory = settings.retrieval_index_dir / "snapshots" / snapshot_id
    if not (directory / "manifest.json").exists():
        atomic_json(directory / "corpus.json", rows)
        atomic_json(directory / "graph.json", graph)
        atomic_json(
            directory / "lexical.json",
            {
                "corpus_version": version,
                "chunk_ids": [row["chunk_id"] for row in rows],
                "tokens": [tokenize(row["text"]) for row in rows],
            },
        )
        atomic_json(
            directory / "manifest.json",
            {
                **identity,
                "snapshot_id": snapshot_id,
                "checksums": {
                    name: file_hash(directory / name)
                    for name in ("corpus.json", "graph.json", "lexical.json")
                },
            },
        )
    load_snapshot(settings.retrieval_index_dir, snapshot_id, settings)
    if activate:
        if settings.graph_backend == "neo4j":
            from ingestion.migrate_neo4j import migrate_snapshot

            migrate_snapshot(settings, snapshot_id)
        atomic_json(settings.retrieval_index_dir / "active.json", {"snapshot_id": snapshot_id})
    return {
        "snapshot_id": snapshot_id,
        "corpus_version": version,
        "chunks": len(rows),
        "entities": len(graph["entities"]),
        "relations": len(graph["relations"]),
        "evidence": len(graph["evidence"]),
        "activated": activate,
        "embedding_requests": 0,
        "collection": store.collection.name,
    }


def main() -> None:
    """Xây hoặc công bố snapshot đã kiểm tra từ collection được chọn."""
    parser = argparse.ArgumentParser(description="Xây GraphRAG/BM25 không gọi Gemini")
    parser.add_argument("--collection")
    parser.add_argument("--activate", action="store_true")
    parser.add_argument("--ontology", type=Path, default=ROOT / "data/knowledge/ontology.json")
    parser.add_argument(
        "--annotations", type=Path, default=ROOT / "data/knowledge/graph_annotations.json"
    )
    args = parser.parse_args()
    settings = get_settings()
    if args.collection:
        settings = settings.model_copy(update={"chroma_collection": args.collection})
    report = build_snapshot(
        settings,
        VectorStore(settings, create=False),
        json.loads(args.ontology.read_text(encoding="utf-8")),
        json.loads(args.annotations.read_text(encoding="utf-8")),
        activate=args.activate,
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
