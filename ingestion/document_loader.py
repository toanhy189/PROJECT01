"""Đọc tài liệu nguồn và giữ thông tin xuất xứ cho từng tài liệu."""

from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from ingestion.parsers import read_docx, read_pdf, read_utf8
from ingestion.text_cleaner import clean_text

MetadataValue = str | int | float | bool


@dataclass(frozen=True)
class Document:
    """Lưu văn bản đã làm sạch cùng ID, tiêu đề và URL nguồn."""

    document_id: str
    title: str
    source_url: str
    text: str
    source_type: str = "md"
    metadata: dict[str, MetadataValue] = field(default_factory=dict)


def valid_source_url(url: str) -> bool:
    """Chỉ chấp nhận HTTPS và các miền nguồn có trong danh sách duyệt."""
    if not isinstance(url, str):
        return False
    try:
        parsed = urlparse(url)
        if parsed.username or parsed.password or parsed.port not in {None, 443}:
            return False
    except ValueError:
        return False
    if parsed.scheme == "https" and parsed.hostname in {"en.wikipedia.org", "vi.wikipedia.org"}:
        revision = parse_qs(parsed.query).get("oldid", [""])
        return (
            parsed.path == "/w/index.php"
            and set(parse_qs(parsed.query)) == {"oldid"}
            and len(revision) == 1
            and revision[0].isdigit()
            and int(revision[0]) > 0
        )
    return parsed.scheme == "https" and parsed.hostname in {
        "www.niddk.nih.gov",
        "www.cdc.gov",
        "www.who.int",
        "www.nhlbi.nih.gov",
    }


def load_document(path: Path, document_id: str, title: str, source_url: str) -> Document:
    """Chuẩn hóa PDF, DOCX, TXT và Markdown về cùng cấu trúc cho chunker."""
    if not valid_source_url(source_url):
        raise ValueError(
            "Nguồn phải thuộc miền đã duyệt; Wikipedia cần URL phiên bản oldid hợp lệ."
        )
    source_type = path.suffix.lower().lstrip(".")
    metadata: dict[str, MetadataValue] = {}
    if source_type == "pdf":
        text, metadata = read_pdf(path)
    elif source_type == "docx":
        text = read_docx(path)
    elif source_type in {"md", "txt"}:
        text = read_utf8(path)
    elif source_type == "doc":
        raise ValueError(
            "Chưa hỗ trợ DOC cũ. Hãy chuyển sang DOCX bằng LibreOffice hoặc Word trước."
        )
    else:
        raise ValueError("Chỉ hỗ trợ PDF có text, DOCX, TXT UTF-8 hoặc Markdown.")
    text = clean_text(text)
    if not text:
        raise ValueError("Tài liệu không có văn bản; không index nội dung rỗng.")
    return Document(document_id, title, source_url, text, source_type, metadata)
