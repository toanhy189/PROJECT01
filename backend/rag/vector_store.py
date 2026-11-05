"""Lưu và tìm chunk trong ChromaDB bền vững với embedding được cung cấp sẵn."""

import chromadb

from backend.core.config import Settings
from backend.core.errors import ServiceError
from ingestion.chunker import Chunk


class VectorStore:
    """Quản lý collection cosine, metadata embedding và cập nhật tài liệu lặp lại."""

    def __init__(self, settings: Settings, *, create: bool = True) -> None:
        """Mở collection và từ chối trộn model hoặc dimension khác chỉ mục cũ."""
        self.settings = settings
        self.client = chromadb.PersistentClient(path=str(settings.chroma_dir))
        metadata = {
            "embedding_model": settings.gemini_embedding_model,
            "embedding_dimension": settings.embedding_dimension,
        }
        if create:
            self.collection = self.client.get_or_create_collection(
                name=settings.chroma_collection,
                metadata=metadata,
                configuration={"hnsw": {"space": "cosine"}},
                embedding_function=None,
            )
        else:
            self.collection = self.client.get_collection(
                name=settings.chroma_collection, embedding_function=None
            )
        existing = self.collection.metadata or {}
        # Hai vector cùng chiều vẫn không tương thích nếu sinh từ hai model khác nhau.
        if any(existing.get(key) != value for key, value in metadata.items()):
            raise ServiceError(
                "Embedding model/dimension khác chỉ mục. Dùng collection mới và re-index.",
                "embedding_mismatch",
            )

    def document_matches(self, document_id: str, chunks: list[Chunk]) -> bool:
        """So sánh nội dung và metadata để bỏ qua tài liệu chưa thay đổi."""
        stored = self.collection.get(
            where={"document_id": document_id}, include=["documents", "metadatas"]
        )
        current = {
            chunk_id: (text, metadata)
            for chunk_id, text, metadata in zip(
                stored["ids"], stored["documents"], stored["metadatas"]
            )
        }
        return bool(chunks) and current == {
            chunk.chunk_id: (chunk.text, chunk.metadata) for chunk in chunks
        }

    def replace_document(
        self, document_id: str, chunks: list[Chunk], vectors: list[list[float]]
    ) -> None:
        """Upsert các chunk hiện tại rồi xóa chunk cũ thuộc cùng tài liệu."""
        if not chunks or len(chunks) != len(vectors):
            raise ValueError("Số chunk và embedding không khớp hoặc rỗng.")
        if len({chunk.chunk_id for chunk in chunks}) != len(chunks) or any(
            chunk.metadata.get("document_id") != document_id for chunk in chunks
        ):
            raise ValueError("Chunk trùng ID hoặc không thuộc tài liệu đang cập nhật.")
        # Upsert trước rồi mới xóa chunk cũ để lỗi API không làm mất tài liệu.
        self.collection.upsert(
            ids=[chunk.chunk_id for chunk in chunks],
            embeddings=vectors,
            documents=[chunk.text for chunk in chunks],
            metadatas=[chunk.metadata for chunk in chunks],
        )
        old_ids = self.collection.get(where={"document_id": document_id})["ids"]
        retained = {chunk.chunk_id for chunk in chunks}
        stale = [chunk_id for chunk_id in old_ids if chunk_id not in retained]
        if stale:
            self.collection.delete(ids=stale)

    def search(self, vector: list[float], k: int) -> dict:
        """Tìm tối đa k chunk gần nhất, giới hạn theo số chunk thực có."""
        count = self.collection.count()
        if count == 0:
            return {"ids": [[]], "documents": [[]], "metadatas": [[]], "distances": [[]]}
        return self.collection.query(
            query_embeddings=[vector],
            n_results=min(k, count),
            include=["documents", "metadatas", "distances"],
        )
