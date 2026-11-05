"""Định danh corpus và kiểm tra provenance dùng chung giữa các chỉ mục."""

import hashlib
import json
from pathlib import Path
from urllib.parse import urlparse

from backend.rag.models import Evidence
from ingestion.document_loader import valid_source_url


def fingerprint(value: object) -> str:
    """Băm dữ liệu JSON chuẩn hóa, không phụ thuộc thứ tự khóa."""
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, ensure_ascii=False).encode()
    ).hexdigest()


def canonical_rows(rows: list[dict]) -> list[dict]:
    """Chuẩn hóa thứ tự chunk trước khi tạo phiên bản corpus."""
    return sorted(rows, key=lambda row: row["chunk_id"])


def collection_rows(collection: object) -> list[dict]:
    """Đọc nội dung/metadata hiện hành, không yêu cầu Chroma tạo embedding."""
    result = collection.get(include=["documents", "metadatas"])
    return canonical_rows(
        [
            {"chunk_id": cid, "text": text, "metadata": metadata}
            for cid, text, metadata in zip(result["ids"], result["documents"], result["metadatas"])
        ]
    )


def provider(metadata: dict) -> str:
    """Nhận nguồn cung cấp mà không đổi ý nghĩa source_type hiện có."""
    host = urlparse(str(metadata.get("source_url", ""))).hostname or ""
    if host in {"en.wikipedia.org", "vi.wikipedia.org"}:
        return "wikipedia"
    if metadata.get("source_provider"):
        return metadata["source_provider"]
    return (
        "wikipedia"
        if host.endswith(".wikipedia.org")
        else "niddk"
        if "niddk" in host
        else "official"
    )


def valid_row(row: dict) -> bool:
    """Từ chối chunk thiếu danh tính, nội dung hoặc URL nguồn được duyệt."""
    meta = row.get("metadata", {})
    return bool(
        row.get("text")
        and row.get("chunk_id") == meta.get("chunk_id")
        and all(
            isinstance(meta.get(k), str) and meta[k].strip()
            for k in ("document_id", "title", "section", "source_url")
        )
        and valid_source_url(meta["source_url"])
    )


def document_versions(rows: list[dict]) -> dict[str, str]:
    """Gắn phiên bản nguồn cho evidence, ưu tiên revision nếu có."""
    grouped: dict[str, list[dict]] = {}
    for row in rows:
        grouped.setdefault(row["metadata"]["document_id"], []).append(row)
    return {
        key: str(group[0]["metadata"].get("content_version") or fingerprint(canonical_rows(group)))
        for key, group in grouped.items()
    }


def row_evidence(row: dict, channel: str) -> Evidence:
    """Chuyển bản snapshot thành candidate không giả lập điểm cosine."""
    return Evidence(row["text"], row["metadata"].copy(), channels=[channel])


def atomic_json(path: Path, value: object) -> None:
    """Chỉ công bố file JSON hoàn chỉnh sau khi ghi xong."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(path)
