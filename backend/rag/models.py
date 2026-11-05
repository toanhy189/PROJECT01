"""Dữ liệu truy xuất dùng chung, tách khoảng cách vector khỏi điểm hợp nhất."""

from dataclasses import dataclass, field

from ingestion.document_loader import MetadataValue


@dataclass
class Evidence:
    """Lưu chunk nguồn và tín hiệu truy xuất; chỉ vector mới có khoảng cách cosine."""

    text: str
    metadata: dict[str, MetadataValue]
    distance: float | None = None
    channels: list[str] = field(default_factory=list)
    score: float = 0.0
    graph_paths: list[dict] = field(default_factory=list)


@dataclass
class RetrievalResult:
    """Giữ bằng chứng và trace riêng từng yêu cầu để không lẫn dữ liệu đồng thời."""

    documents: list[Evidence]
    trace: dict = field(default_factory=dict)
