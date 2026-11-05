"""Biểu diễn bảng văn bản nhất quán cho parser HTML và DOCX."""


def markdown_table(rows: list[list[str]]) -> str:
    """Giữ ô rỗng, xuống dòng và dấu gạch đứng khi chuyển bảng sang Markdown."""
    if not rows or not any(rows):
        return ""
    width = max(len(row) for row in rows)
    lines = []
    for row in rows:
        cells = [
            cell.replace("\\", "\\\\").replace("|", "\\|").replace("\n", "<br>") for cell in row
        ]
        cells.extend([""] * (width - len(cells)))
        lines.append("| " + " | ".join(cells) + " |")
    lines.insert(1, "| " + " | ".join(["---"] * width) + " |")
    return "\n".join(lines)
