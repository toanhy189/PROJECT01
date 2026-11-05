"""Đọc snapshot bất biến và chuyển phiên bản corpus bằng một con trỏ nguyên tử."""

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path

from backend.core.config import Settings
from backend.rag.corpus import canonical_rows, collection_rows, fingerprint, valid_row
from backend.rag.graph_backend import GraphBackend
from backend.rag.knowledge_graph import KnowledgeGraph
from backend.rag.lexical import LexicalIndex, tokenize
from backend.rag.vector_store import VectorStore


@dataclass
class RetrievalSnapshot:
    """Gom corpus, BM25, graph và Chroma cùng phiên bản để phục vụ một yêu cầu."""

    snapshot_id: str
    corpus_version: str
    rows: list[dict]
    graph: GraphBackend
    lexical: LexicalIndex
    store: VectorStore


def file_hash(path: Path) -> str:
    """Băm nội dung file để phát hiện snapshot ghi thiếu hoặc bị sửa."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_snapshot(root: Path, snapshot_id: str, settings: Settings) -> RetrievalSnapshot:
    """Từ chối snapshot sai checksum, cấu hình embedding hoặc phiên bản Chroma."""
    if not re.fullmatch(r"[a-f0-9]{64}", snapshot_id):
        raise ValueError("Snapshot ID không hợp lệ.")
    directory = root / "snapshots" / snapshot_id
    manifest = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
    if manifest.get("snapshot_id") != snapshot_id:
        raise ValueError("Danh tính snapshot không khớp.")
    for name in ("corpus.json", "graph.json", "lexical.json"):
        if file_hash(directory / name) != manifest["checksums"].get(name):
            raise ValueError("Snapshot không khớp checksum.")
    if (
        manifest["embedding_model"] != settings.gemini_embedding_model
        or manifest["embedding_dimension"] != settings.embedding_dimension
    ):
        raise ValueError("Snapshot không cùng cấu hình embedding.")
    rows = canonical_rows(json.loads((directory / "corpus.json").read_text(encoding="utf-8")))
    if (
        not rows
        or len({row["chunk_id"] for row in rows}) != len(rows)
        or not all(map(valid_row, rows))
    ):
        raise ValueError("Corpus snapshot rỗng hoặc chunk không hợp lệ.")
    version = fingerprint(rows)
    lexical = json.loads((directory / "lexical.json").read_text(encoding="utf-8"))
    if version != manifest["corpus_version"] or lexical["corpus_version"] != version:
        raise ValueError("Các chỉ mục không cùng phiên bản corpus.")
    if lexical["chunk_ids"] != [row["chunk_id"] for row in rows] or lexical["tokens"] != [
        tokenize(row["text"]) for row in rows
    ]:
        raise ValueError("BM25 không trỏ đúng corpus.")
    graph_data = json.loads((directory / "graph.json").read_text(encoding="utf-8"))
    if fingerprint(graph_data) != manifest["graph_hash"]:
        raise ValueError("Graph hash không khớp manifest.")
    if settings.graph_backend == "neo4j":
        from backend.rag.neo4j_graph import Neo4jGraph

        graph = Neo4jGraph(graph_data, rows, settings, snapshot_id, manifest["graph_hash"])
    else:
        graph = KnowledgeGraph(graph_data, rows)
    store = VectorStore(
        settings.model_copy(update={"chroma_collection": manifest["collection"]}), create=False
    )
    if fingerprint(collection_rows(store.collection)) != version:
        raise ValueError("Chroma đã thay đổi so với snapshot; dùng fallback vector.")
    return RetrievalSnapshot(
        snapshot_id, version, rows, graph, LexicalIndex(rows, graph.entities), store
    )


def load_active_snapshot(settings: Settings) -> RetrievalSnapshot:
    """Mở đúng snapshot đã công bố, không tự ghép graph mới với BM25 cũ."""
    active = json.loads((settings.retrieval_index_dir / "active.json").read_text(encoding="utf-8"))
    return load_snapshot(settings.retrieval_index_dir, active["snapshot_id"], settings)
