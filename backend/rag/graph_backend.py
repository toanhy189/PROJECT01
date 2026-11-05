"""Giao diện nhỏ cho hai backend graph, không phụ thuộc driver trong Agent."""

from typing import Protocol

from backend.rag.knowledge_graph import Relation
from backend.rag.models import Evidence


class GraphBackend(Protocol):
    """Đầu ra truy xuất thống nhất để tiếp tục dùng fusion và context hiện có."""

    entities: list[dict]
    relations: dict[str, Relation]
    evidence: dict[str, list[dict]]

    def search(
        self, question: str, limit: int = 15, max_hops: int = 2, max_paths: int = 40
    ) -> tuple[list[Evidence], dict]:
        """Trả candidate đã xếp hạng và trace của backend thực sự truy vấn."""
        ...
