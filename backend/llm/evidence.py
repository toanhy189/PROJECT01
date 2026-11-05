"""Đánh mã đoạn nguồn để Gemini chọn bằng chứng thay vì chép lại văn bản."""

import re
from dataclasses import dataclass

WIKI_NOTE = "Nguồn bách khoa bổ sung; chỉ dùng cho định nghĩa/kiến thức nền.\n"
SOURCE_HEADER = re.compile(r"^\[(S[1-9]\d*)\] ([^\n]+ — [^\n]+)\n", re.MULTILINE)


@dataclass(frozen=True)
class EvidencePassage:
    """Giữ vị trí nguyên văn trong chunk để lấy lại cả khoảng giữa các đoạn."""

    citation_id: str
    heading: str
    source_text: str
    start: int
    end: int
    background_only: bool = False

    @property
    def text(self) -> str:
        """Trả đoạn gốc, giữ nguyên bảng, danh sách, số liệu và dấu phủ định."""
        return self.source_text[self.start : self.end]


def build_passage_catalog(context: str) -> dict[str, EvidencePassage]:
    """Đọc các khối do context builder tạo; không sửa văn bản đã truy xuất."""
    headers = list(SOURCE_HEADER.finditer(context))
    catalog = {}
    for index, header in enumerate(headers):
        end = headers[index + 1].start() if index + 1 < len(headers) else len(context)
        source_block = context[header.end() : end]
        background_only = source_block.startswith(WIKI_NOTE)
        source_text = source_block.removeprefix(WIKI_NOTE).strip()
        citation_id, heading = header.groups()
        for number, paragraph in enumerate(
            re.finditer(r"\S[\s\S]*?(?=\n[ \t]*\n|\Z)", source_text), start=1
        ):
            passage_id = f"{citation_id}.P{number}"
            if passage_id in catalog:
                raise ValueError("Context chứa mã nguồn trùng.")
            catalog[passage_id] = EvidencePassage(
                citation_id,
                heading,
                source_text,
                paragraph.start(),
                paragraph.end(),
                background_only,
            )
    return catalog


def resolve_passages(passage_ids: list[str], catalog: dict[str, EvidencePassage]) -> dict[str, str]:
    """Lấy quote từ nguồn; nhiều đoạn cùng nguồn thành một khoảng liên tục."""
    if not passage_ids or len(set(passage_ids)) != len(passage_ids):
        raise ValueError("Mã đoạn bằng chứng thiếu hoặc trùng.")
    grouped: dict[str, list[EvidencePassage]] = {}
    for passage_id in passage_ids:
        if passage_id not in catalog:
            raise ValueError("Mã đoạn bằng chứng không có trong yêu cầu hiện tại.")
        passage = catalog[passage_id]
        grouped.setdefault(passage.citation_id, []).append(passage)
    if len(grouped) > 5:
        raise ValueError("Nhận định dẫn quá nhiều nguồn.")
    # Giữ cả nội dung nằm giữa, tránh ghép câu rời hoặc vô tình bỏ dấu phủ định.
    return {
        citation_id: passages[0].source_text[
            min(item.start for item in passages) : max(item.end for item in passages)
        ]
        for citation_id, passages in grouped.items()
    }
