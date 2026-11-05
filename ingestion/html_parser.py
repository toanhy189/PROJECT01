"""Trích nội dung HTML theo thứ tự DOM, giữ heading, bảng và chú thích."""

import re
from collections.abc import Iterator

from bs4 import BeautifulSoup, Comment, NavigableString, Tag

from ingestion.table_formatter import markdown_table

BLOCK_TAGS = {
    "p",
    "div",
    "section",
    "article",
    "aside",
    "blockquote",
    "figure",
    "figcaption",
    "ul",
    "ol",
    "li",
    "dl",
    "dt",
    "dd",
    "table",
    "h1",
    "h2",
    "h3",
    "h4",
    "h5",
    "h6",
}


def inline_text(node: Tag | NavigableString) -> str:
    """Giữ khoảng trắng gốc giữa thẻ inline, xuống dòng và ký hiệu mũ/chỉ số."""
    if isinstance(node, Comment):
        return ""
    if isinstance(node, NavigableString):
        return re.sub(r"\s+", " ", str(node))
    text = "".join(inline_text(child) for child in node.children)
    if node.name == "br":
        return "\n" + text
    if node.name in {"sup", "sub"}:
        return f"<{node.name}>{text}</{node.name}>"
    return text


def html_table(table: Tag) -> str:
    """Giữ hàng/cột và mở rộng ô gộp để giá trị vẫn gắn với đúng cột."""
    grid: dict[tuple[int, int], str] = {}
    rows = [row for row in table.find_all("tr") if row.find_parent("table") is table]
    for row_index, row in enumerate(rows):
        column = 0
        for cell in row.find_all(["td", "th"], recursive=False):
            while (row_index, column) in grid:
                column += 1
            text = "\n".join(html_blocks(cell)).strip()
            rowspan = int(cell.get("rowspan", 1))
            colspan = int(cell.get("colspan", 1))
            if not 1 <= rowspan <= 1000 or not 1 <= colspan <= 1000:
                raise ValueError("Kích thước ô gộp HTML không hợp lệ; cần kiểm tra bảng.")
            for row_offset in range(rowspan):
                for column_offset in range(colspan):
                    grid[row_index + row_offset, column + column_offset] = text
            column += colspan
    if not grid:
        return ""
    height = max(row for row, _ in grid) + 1
    width = max(column for _, column in grid) + 1
    body = markdown_table(
        [[grid.get((row, column), "") for column in range(width)] for row in range(height)]
    )
    caption = table.find("caption", recursive=False)
    return f"{inline_text(caption).strip()}\n\n{body}" if caption else body


def html_blocks(container: Tag) -> Iterator[str]:
    """Đọc mỗi khối đúng một lần, kể cả văn bản trực tiếp trong div hoặc span."""
    pending: list[str] = []
    attached_notes: list[Tag] = []
    for child in container.children:
        if any(child is note for note in attached_notes):
            continue
        if isinstance(child, Comment):
            continue
        if isinstance(child, Tag) and child.name in BLOCK_TAGS:
            text = "".join(pending).strip()
            if text:
                yield text
            pending = []
            if re.fullmatch(r"h[1-6]", child.name):
                text = inline_text(child).strip()
                if text:
                    yield f"{'#' * int(child.name[1])} {text}"
            elif child.name == "table":
                text = html_table(child)
                note = child.find_next_sibling()
                if (
                    note is not None
                    and note.name == "aside"
                    and "references" in note.get("class", [])
                    and re.match(r"^[*†‡]", note.get_text(strip=True))
                ):
                    # Chú thích điều kiện xét nghiệm phải đi cùng bảng khi truy xuất.
                    text += "\n" + "\n".join(html_blocks(note))
                    attached_notes.append(note)
                if text:
                    yield text
            elif child.name in {"ul", "ol"}:
                items = []
                for index, item in enumerate(child.find_all("li", recursive=False), 1):
                    text = "\n".join(html_blocks(item))
                    prefix = f"{index}. " if child.name == "ol" else "- "
                    if text:
                        items.append(prefix + text.replace("\n", "\n  "))
                if items:
                    yield "\n".join(items)
            else:
                yield from html_blocks(child)
        else:
            pending.append(inline_text(child))
    text = "".join(pending).strip()
    if text:
        yield text


def remove_navigation(article: Tag) -> None:
    """Chỉ bỏ điều hướng đã nhận diện; giữ aside chứa tham khảo và cảnh báo."""
    for element in article.select(
        "script, style, nav, form, img, svg, footer, iframe, noscript, button, input, "
        "[role='navigation']"
    ):
        element.decompose()
    heading_ids = {tag.get("id") for tag in article.select("h1, h2, h3, h4, h5, h6")}
    for label in list(article.find_all("p")):
        if label.get_text(" ", strip=True).casefold() != "in this section:":
            continue
        listing = label.find_next_sibling()
        if listing is None or listing.name not in {"ul", "ol"}:
            continue
        items = listing.find_all("li", recursive=False)
        if items and all(
            len(item.find_all("a")) == 1
            and item.get_text(" ", strip=True) == item.a.get_text(" ", strip=True)
            and str(item.a.get("href", "")).startswith("#")
            and str(item.a["href"])[1:] in heading_ids
            for item in items
        ):
            listing.decompose()
            label.decompose()


def extract_article(html: str) -> str:
    """Lấy vùng bài viết chính; không khử trùng toàn cục làm mất kiến thức lặp."""
    soup = BeautifulSoup(html, "html.parser")
    article = soup.select_one(".health-detail-content") or soup.select_one("article")
    if article is None:
        raise ValueError("Không tìm thấy nội dung bài; cần kiểm tra selector.")
    remove_navigation(article)
    body = "\n\n".join(html_blocks(article))
    if not body.strip():
        raise ValueError("Nội dung bài rỗng sau khi trích xuất.")
    return body
