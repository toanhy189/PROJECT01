"""Tạo embedding Gemini cho tài liệu và câu hỏi trong cùng không gian vector."""

from contextlib import nullcontext

import httpx
import numpy as np
from google import genai
from google.genai import errors, types

from backend.core.config import Settings
from backend.core.errors import ServiceError
from backend.llm.client import make_client


class EmbeddingService:
    """Bao bọc Gemini embedding, kiểm tra kích thước và chuẩn hóa vector."""

    def __init__(self, settings: Settings, client: genai.Client | None = None) -> None:
        """Giữ cấu hình embedding và client tùy chọn phục vụ kiểm thử."""
        self.settings = settings
        self.client = client

    def embed(self, texts: list[str], *, query: bool = False) -> list[list[float]]:
        """Chọn task query/document, kiểm tra vector hữu hạn và chuẩn hóa L2."""
        if not texts:
            return []
        try:
            with nullcontext(self.client) if self.client else make_client(self.settings) as client:
                result = client.models.embed_content(
                    model=self.settings.gemini_embedding_model,
                    contents=texts,
                    config=types.EmbedContentConfig(
                        task_type="RETRIEVAL_QUERY" if query else "RETRIEVAL_DOCUMENT",
                        output_dimensionality=self.settings.embedding_dimension,
                    ),
                )
            vectors = np.asarray([item.values for item in result.embeddings], dtype=np.float32)
        except (errors.APIError, httpx.HTTPError, TimeoutError, ValueError, TypeError) as exc:
            raise ServiceError(
                "Không thể lấy embedding từ Gemini. Vui lòng thử lại.", "embedding_unavailable"
            ) from exc
        if (
            vectors.shape != (len(texts), self.settings.embedding_dimension)
            or not np.isfinite(vectors).all()
        ):
            raise ServiceError("Embedding trả về sai kích thước hoặc giá trị.", "embedding_invalid")
        norms = np.linalg.norm(vectors, axis=1, keepdims=True)
        if (norms <= 0).any():
            raise ServiceError("Gemini trả về vector rỗng.", "embedding_invalid")
        # Vector rút gọn của gemini-embedding-001 cần chuẩn hóa L2.
        return (vectors / norms).tolist()
