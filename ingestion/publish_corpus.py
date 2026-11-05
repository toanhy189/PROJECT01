"""Chuẩn bị collection mới bằng vector đã có, kiểm tra xong mới công bố snapshot."""

import argparse
import json
from pathlib import Path

import numpy as np
from chromadb.errors import NotFoundError

from backend.core.config import ROOT, Settings, get_settings
from backend.core.errors import ServiceError
from backend.rag.corpus import collection_rows, fingerprint
from backend.rag.embedding_service import EmbeddingService
from backend.rag.snapshot import load_active_snapshot
from backend.rag.vector_store import VectorStore
from ingestion.build_retrieval_indexes import build_snapshot
from ingestion.chunker import chunk_document
from ingestion.document_loader import Document
from ingestion.wiki_sources import load_wiki_documents


def publish_corpus(
    settings: Settings,
    base_store: VectorStore,
    additions: list[Document],
    ontology: dict,
    annotations: list[dict],
    embeddings: EmbeddingService,
    *,
    activate: bool = False,
) -> dict:
    """Giữ collection cũ; chỉ gọi embedding cho văn bản mới và chuyển active sau kiểm tra."""
    stored = base_store.collection.get(include=["documents", "metadatas", "embeddings"])
    rows = {
        cid: {"chunk_id": cid, "text": text, "metadata": metadata}
        for cid, text, metadata in zip(stored["ids"], stored["documents"], stored["metadatas"])
    }
    vectors = {
        fingerprint(text): vector.tolist()
        for text, vector in zip(stored["documents"], stored["embeddings"])
    }
    requests, created = 0, []
    for document in additions:
        # Một revision mới thay toàn bộ chunk thuộc đúng document ID đó trong bản mới.
        rows = {
            cid: row
            for cid, row in rows.items()
            if row["metadata"]["document_id"] != document.document_id
        }
        chunks = chunk_document(document)
        if not chunks:
            raise ValueError("Tài liệu bổ sung không tạo được chunk.")
        for chunk in chunks:
            rows[chunk.chunk_id] = {
                "chunk_id": chunk.chunk_id,
                "text": chunk.text,
                "metadata": chunk.metadata,
            }
    ordered = sorted(rows.values(), key=lambda row: row["chunk_id"])
    version = fingerprint(ordered)
    collection_name = f"diabetes_snapshot_{version[:24]}"
    target_settings = settings.model_copy(update={"chroma_collection": collection_name})
    try:
        existing = VectorStore(target_settings, create=False)
    except NotFoundError:
        existing = None
    if existing and fingerprint(collection_rows(existing.collection)) == version:
        return {
            **build_snapshot(target_settings, existing, ontology, annotations, activate=activate),
            "new_embedding_texts": 0,
            "reused_vectors": len(ordered),
        }
    if existing:
        active = settings.retrieval_index_dir / "active.json"
        if active.exists():
            snapshot_id = json.loads(active.read_text(encoding="utf-8"))["snapshot_id"]
            active_manifest = json.loads(
                (
                    settings.retrieval_index_dir / "snapshots" / snapshot_id / "manifest.json"
                ).read_text(encoding="utf-8")
            )
            if active_manifest["collection"] == collection_name:
                raise ValueError("Collection active không khớp corpus; không sửa bản đang phục vụ.")
        cached = existing.collection.get(include=["documents", "embeddings"])
        vectors.update(
            {
                fingerprint(text): vector.tolist()
                for text, vector in zip(cached["documents"], cached["embeddings"])
            }
        )
    missing = list({row["text"] for row in ordered if fingerprint(row["text"]) not in vectors})
    missing.sort()
    for offset in range(0, len(missing), 16):
        batch = missing[offset : offset + 16]
        generated = embeddings.embed(batch)
        if len(generated) != len(batch):
            raise ValueError("Embedding không đủ; không công bố corpus mới.")
        vectors.update({fingerprint(text): vector for text, vector in zip(batch, generated)})
        created.extend(batch)
        requests += 1
    matrix = np.asarray([vectors[fingerprint(row["text"])] for row in ordered])
    if (
        matrix.shape != (len(ordered), settings.embedding_dimension)
        or not np.isfinite(matrix).all()
        or not np.allclose(np.linalg.norm(matrix, axis=1), 1, atol=1e-5)
    ):
        raise ValueError("Vector corpus không hữu hạn/đúng chiều/chuẩn hóa.")
    target = existing or VectorStore(target_settings)
    # Ghi collection mới; lỗi không đụng con trỏ hoặc collection baseline.
    for offset in range(0, len(ordered), 128):
        batch = ordered[offset : offset + 128]
        target.collection.upsert(
            ids=[r["chunk_id"] for r in batch],
            documents=[r["text"] for r in batch],
            metadatas=[r["metadata"] for r in batch],
            embeddings=matrix[offset : offset + 128].tolist(),
        )
    stale = set(target.collection.get()["ids"]) - set(rows)
    if stale:
        target.collection.delete(ids=sorted(stale))
    report = build_snapshot(target_settings, target, ontology, annotations, activate=activate)
    report.update(
        embedding_requests=requests,
        new_embedding_texts=len(created),
        reused_vectors=len(ordered) - len(created),
    )
    return report


def publish_wiki(settings: Settings, manifest: Path, *, activate: bool = False) -> dict:
    """Kiểm tra đủ nguồn wiki trước khi chuẩn bị collection mới."""
    # Đọc/kiểm tra toàn bộ wiki trước khi mở hoặc thay chỉ mục.
    documents = load_wiki_documents(manifest)
    try:
        base = load_active_snapshot(settings).store
    except (OSError, ValueError, KeyError):
        base = VectorStore(settings, create=False)
    return publish_corpus(
        settings,
        base,
        documents,
        json.loads((ROOT / "data/knowledge/ontology.json").read_text(encoding="utf-8")),
        json.loads((ROOT / "data/knowledge/graph_annotations.json").read_text(encoding="utf-8")),
        EmbeddingService(settings),
        activate=activate,
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Bổ sung wiki vào corpus phiên bản mới")
    parser.add_argument("--wiki-manifest", type=Path, default=ROOT / "data/wiki/manifest.json")
    parser.add_argument("--activate", action="store_true")
    args = parser.parse_args()
    try:
        result = publish_wiki(get_settings(), args.wiki_manifest, activate=args.activate)
    except (OSError, ValueError, KeyError, ServiceError) as exc:
        print(
            json.dumps(
                {
                    "status": "not_published",
                    "error_type": type(exc).__name__,
                    "hint": "Cần tải đủ wiki hợp lệ và kiểm tra nguồn/embedding trước khi publish.",
                    "activated": False,
                },
                ensure_ascii=False,
            )
        )
        raise SystemExit(1) from None
    print(json.dumps(result, ensure_ascii=False, indent=2))
