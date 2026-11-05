"""Đọc từng định dạng thành văn bản, không tạo tệp chuyển đổi trung gian."""

import re
from pathlib import Path
from zipfile import BadZipFile

import pymupdf
from docx import Document as open_docx
from docx.document import Document as DocxDocument
from docx.opc.exceptions import PackageNotFoundError
from docx.styles.style import ParagraphStyle
from docx.table import Table, _Cell
from docx.text.paragraph import Paragraph
from lxml.etree import XMLSyntaxError

from ingestion.table_formatter import markdown_table


class OCRRequiredError(ValueError):
    """Báo trang thiếu lớp text để bổ sung OCR riêng khi cần triển khai."""


def read_utf8(path: Path) -> str:
    """Đọc UTF-8/BOM nghiêm ngặt, không thay ký tự lỗi hoặc đoán bảng mã."""
    try:
        return path.read_text(encoding="utf-8-sig")
    except UnicodeDecodeError as exc:
        raise ValueError(
            "Tệp không phải UTF-8 hợp lệ; hãy lưu lại bằng UTF-8 trước khi index."
        ) from exc


def read_pdf(path: Path) -> tuple[str, dict[str, int]]:
    """Đọc text theo vị trí trang; chặn cả PDF scan lẫn PDF thiếu text một phần."""
    try:
        with pymupdf.open(path) as pdf:
            if pdf.needs_pass:
                raise ValueError("PDF có mật khẩu; cần mở khóa trước khi index.")
            pages = [page.get_text(sort=True).strip() for page in pdf]
    except pymupdf.FileDataError as exc:
        raise ValueError("Không đọc được PDF; tệp có thể bị hỏng.") from exc
    empty_pages = [str(index) for index, text in enumerate(pages, 1) if not text]
    if not pages or empty_pages:
        detail = ", ".join(empty_pages) or "toàn bộ tài liệu"
        raise OCRRequiredError(
            f"PDF không có text ở trang {detail}. Cần kiểm tra trang trống hoặc OCR "
            "nếu là trang scan; OCR chưa được bật/triển khai. Không index thiếu trang."
        )
    return "\n\n".join(pages), {"page_count": len(pages)}


def heading_level(paragraph: Paragraph) -> int | None:
    """Nhận cấp heading từ style, outline trực tiếp hoặc style kế thừa."""
    properties = paragraph._p.pPr
    if properties is not None and properties.outlineLvl is not None:
        level = properties.outlineLvl.val
        return min(level + 1, 6) if level < 9 else None
    style: ParagraphStyle | None = paragraph.style
    seen = set()
    while style is not None and style.style_id not in seen:
        seen.add(style.style_id)
        match = re.fullmatch(r"Heading\s*([1-9])", style.name or "", re.IGNORECASE)
        if match:
            return min(int(match.group(1)), 6)
        if style.name == "Title":
            return 1
        properties = style.element.pPr
        if properties is not None and properties.outlineLvl is not None:
            level = properties.outlineLvl.val
            return min(level + 1, 6) if level < 9 else None
        style = style.base_style
    return None


def docx_blocks(container: DocxDocument | _Cell) -> list[str]:
    """Duyệt paragraph và bảng theo thứ tự XML, kể cả bảng lồng trong ô."""
    blocks = []
    for block in container.iter_inner_content():
        if isinstance(block, Paragraph):
            text = block.text.strip()
            if text:
                level = heading_level(block)
                blocks.append(f"{'#' * level} {text}" if level else text)
        elif isinstance(block, Table):
            rows = []
            for row in block.rows:
                cells = [""] * row.grid_cols_before
                seen = set()
                for cell in row.cells:
                    # Một ô gộp ngang được python-docx trả lại ở nhiều cột.
                    if cell._tc in seen:
                        cells.append("")
                    else:
                        seen.add(cell._tc)
                        cells.append("\n".join(docx_blocks(cell)))
                cells.extend([""] * row.grid_cols_after)
                rows.append(cells)
            text = markdown_table(rows)
            if text:
                blocks.append(text)
    return blocks


def read_docx(path: Path) -> str:
    """Đọc thân DOCX; báo lỗi rõ ràng nếu gói tài liệu không hợp lệ."""
    try:
        return "\n\n".join(docx_blocks(open_docx(path)))
    except (PackageNotFoundError, BadZipFile, KeyError, XMLSyntaxError) as exc:
        raise ValueError("Không đọc được DOCX; tệp có thể bị hỏng hoặc sai định dạng.") from exc
