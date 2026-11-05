"""Dựng context giới hạn độ dài và danh sách nguồn có ID cho Gemini."""

from backend.rag.corpus import provider
from backend.rag.models import Evidence
from backend.schemas.api import Citation


def build_context(evidence: list[Evidence], max_chars: int = 14000) -> tuple[str, list[Citation]]:
    """Khử chunk trùng, giữ đoạn nguyên vẹn trong ngân sách và gắn ID S1, S2."""
    blocks, citations, seen, seen_text = [], [], set(), set()
    remaining = max_chars
    for item in evidence:
        key = item.metadata["chunk_id"]
        text_key = " ".join(item.text.split())
        if key in seen or text_key in seen_text:
            continue
        citation_id = f"S{len(citations) + 1}"
        prefix = f"[{citation_id}] {item.metadata['title']} — {item.metadata['section']}\n"
        if provider(item.metadata) == "wikipedia":
            prefix += "Nguồn bách khoa bổ sung; chỉ dùng cho định nghĩa/kiến thức nền.\n"
        block = prefix + item.text
        if len(block) > remaining:
            continue
        seen.add(key)
        seen_text.add(text_key)
        blocks.append(block)
        citations.append(Citation(citation_id=citation_id, quote=item.text, **item.metadata))
        remaining -= len(block) + 2
    return "\n\n".join(blocks), citations
