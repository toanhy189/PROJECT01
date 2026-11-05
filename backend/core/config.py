"""Đọc cấu hình backend từ môi trường và chuẩn hóa đường dẫn theo gốc dự án."""

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    """Quản lý khóa backend, model, đường dẫn và giới hạn truy xuất."""

    model_config = SettingsConfigDict(env_file=ROOT / ".env", extra="ignore")

    gemini_api_key: str = Field(default="", repr=False)
    gemini_embedding_model: str = "gemini-embedding-001"
    gemini_llm_model: str = "gemini-2.5-flash"
    embedding_dimension: int = Field(default=768, ge=128, le=3072)
    gemini_timeout_ms: int = Field(default=30000, ge=1000)
    artifact_dir: Path = ROOT / "artifacts"
    chroma_dir: Path = ROOT / "data/chroma"
    chroma_collection: str = "diabetes_knowledge"
    cors_origins: list[str] = ["http://localhost:5173", "http://127.0.0.1:5173"]
    retrieval_k: int = Field(default=5, ge=1, le=20)
    max_cosine_distance: float = Field(default=0.65, ge=0, le=2)
    context_max_chars: int = Field(default=14000, ge=1000)
    retrieval_index_dir: Path = ROOT / "data/retrieval"
    enable_graph_retrieval: bool = False
    enable_hybrid_search: bool = False
    enable_wiki: bool = False
    enable_reranking: bool = False
    graph_backend: Literal["networkx", "neo4j"] = "neo4j"
    neo4j_uri: str = "bolt://127.0.0.1:7687"
    neo4j_user: str = "neo4j"
    neo4j_password: str = Field(default="", repr=False)
    neo4j_database: str = "neo4j"
    neo4j_connection_timeout_seconds: float = Field(default=2, ge=0.1, le=30)
    neo4j_query_timeout_seconds: float = Field(default=2, ge=0.1, le=30)
    neo4j_pool_size: int = Field(default=4, ge=1, le=16)
    graph_expansion_limit: int = Field(default=400, ge=40, le=2000)
    retrieval_candidate_k: int = Field(default=15, ge=5, le=100)
    graph_max_hops: int = Field(default=2, ge=1, le=2)
    graph_max_paths: int = Field(default=40, ge=1, le=100)
    rrf_constant: int = Field(default=60, ge=1, le=1000)
    fusion_policy: Literal["rrf", "vector_guarded"] = "vector_guarded"
    reranker_model: str = "cross-encoder/mmarco-mMiniLMv2-L12-H384-v1"
    reranker_timeout_seconds: float = Field(default=15, ge=1, le=60)
    reranker_max_candidates: int = Field(default=15, ge=5, le=40)
    wiki_user_agent: str = "GlucoGuideAcademicRAG/0.1 (local student project)"

    def model_post_init(self, context: object) -> None:
        """Đổi đường dẫn tương đối thành đường dẫn tính từ thư mục dự án."""
        for name in ("artifact_dir", "chroma_dir", "retrieval_index_dir"):
            path = getattr(self, name)
            if not path.is_absolute():
                setattr(self, name, ROOT / path)


@lru_cache
def get_settings() -> Settings:
    """Dùng lại cấu hình trong process, tránh đọc lại file .env mỗi yêu cầu."""
    return Settings()
