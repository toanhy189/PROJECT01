"""Chia văn bản theo mục và câu, gắn metadata cho từng đoạn truy xuất."""

import hashlib
import math
import re
from dataclasses import dataclass

from ingestion.document_loader import Document, MetadataValue


@dataclass(frozen=True)
class Chunk:
    """Lưu nội dung một đoạn và metadata dùng để truy xuất, trích dẫn."""

    chunk_id: str
    text: str
    metadata: dict[str, MetadataValue]


def estimate_tokens(text: str) -> int:
    """Ước lượng theo ký tự, không thay thế tokenizer riêng của Gemini."""
    return math.ceil(len(text) / 4)


def join_sentences(sentences: list[tuple[str, str]]) -> str:
    """Giữ ranh giới đoạn trong khi vẫn đóng gói và overlap theo câu."""
    return "".join(
        (separator if index else "") + text for index, (text, separator) in enumerate(sentences)
    ).strip()


def chunk_document(
    document: Document, max_tokens: int = 500, overlap_tokens: int = 50
) -> list[Chunk]:
    """Chia theo heading và câu; giữ một phần câu cuối làm vùng chồng lấn."""
    if max_tokens <= 0 or not 0 <= overlap_tokens < max_tokens:
        raise ValueError("Kích thước chunk/overlap không hợp lệ.")
    chunks: list[Chunk] = []
    section = document.title
    pending: list[tuple[str, str]] = []
    headings: list[tuple[int, str]] = []

    def emit() -> None:
        """Lưu phần văn bản đang gom với ID xác định từ nội dung và vị trí."""
        text = join_sentences(pending)
        if not text:
            return
        # Cùng tài liệu, mục, vị trí và nội dung sẽ tạo cùng ID khi index lại.
        digest = hashlib.sha256(
            f"{document.document_id}:{section}:{len(chunks)}:{text}".encode()
        ).hexdigest()[:24]
        chunks.append(
            Chunk(
                digest,
                text,
                {
                    **document.metadata,
                    "document_id": document.document_id,
                    "chunk_id": digest,
                    "title": document.title,
                    "section": section,
                    "source_url": document.source_url,
                    "source_type": document.source_type,
                    "section_path": " > ".join(value for _, value in headings) or section,
                },
            )
        )

    # Heading Markdown không bắt buộc có dòng trống trước/sau.
    text = re.sub(r"(?m)^(#{1,6}[ \t]+[^\n]+)$", r"\n\n\1\n\n", document.text)
    for paragraph in re.split(r"\n\s*\n", text):
        heading = re.match(r"^#{1,6}\s+(.+)$", paragraph.strip())
        if heading:
            # Chốt mục cũ trước khi đổi heading để metadata không gắn nhầm section.
            emit()
            pending = []
            section = heading.group(1)
            level = len(paragraph.strip().split()[0])
            headings = [(depth, value) for depth, value in headings if depth < level]
            headings.append((level, section))
            continue
        if paragraph.lstrip().startswith("|") and re.search(r"(?m)^\|[ :|\-]+\|$", paragraph):
            # Bảng phải nguyên khối để không tách giá trị khỏi tên cột.
            emit()
            pending = [(paragraph.strip(), "")]
            emit()
            pending = []
            continue
        sentences = re.split(r"(?<=[.!?])\s+(?=[A-ZÀ-Ỹ0-9])|\n(?=#+\s)", paragraph)
        for index, sentence in enumerate(sentences):
            sentence = sentence.strip()
            if not sentence:
                continue
            item = (sentence, "\n\n" if index == 0 else " ")
            if pending and estimate_tokens(join_sentences(pending + [item])) > max_tokens:
                emit()
                tail: list[tuple[str, str]] = []
                # Chỉ lặp lại câu nguyên vẹn trong ngân sách overlap, không cắt giữa câu.
                for previous in reversed(pending):
                    if estimate_tokens(join_sentences([previous] + tail)) > overlap_tokens:
                        break
                    tail.insert(0, previous)
                pending = tail
                if estimate_tokens(join_sentences(pending + [item])) > max_tokens:
                    pending = []
            # Giữ nguyên câu quá dài thay vì cắt giữa câu.
            pending.append(item)
    emit()
    return chunks
