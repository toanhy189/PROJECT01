"""Ưu tiên nguồn chính và giới hạn Wikipedia ở kiến thức nền/định nghĩa."""

import re

from backend.rag.corpus import provider
from backend.rag.lexical import normalize_term


def wiki_background_query(question: str) -> bool:
    """Chỉ nhận truy vấn định nghĩa rõ ràng, loại các yêu cầu khuyến nghị y khoa."""
    text = normalize_term(question)
    background = re.search(
        r"\bla gi\b|\bdinh nghia\b|\bthuat ngu\b|\bwhat is\b|\bdefinition\b|\bmeaning\b", text
    )
    clinical = re.search(
        r"lieu|dieu tri|thuoc|ke don|chan doan|nguong|bao nhieu|mg dl|"
        r"nen lam|nen dung|khuyen nghi|nguy co|trieu chung|bien chung|sang loc|"
        r"treatment|dosage|diagnos|cutoff|should i|risk|symptom|complication|screen",
        text,
    )
    return bool(background and not clinical)


def source_allowed(metadata: dict, question: str, enable_wiki: bool) -> bool:
    """Nguồn wiki không được tự trở thành chứng cứ cho câu hỏi điều trị/xét nghiệm."""
    return provider(metadata) != "wikipedia" or (enable_wiki and wiki_background_query(question))


def wiki_claim_allowed(text: str, sources: list[object]) -> bool:
    """Không cho nguồn wiki đơn độc chứng minh số đo hoặc khuyến nghị y khoa."""
    from backend.rag.citation_validator import clinical_numbers

    if not sources or any(provider(source.model_dump()) != "wikipedia" for source in sources):
        return True
    clinical = re.search(
        r"chan doan|nguong|dieu tri|lieu|thuoc|nen dung|nen lam|"
        r"diagnos|treatment|dosage|cutoff|recommend",
        normalize_term(text),
    )
    return not clinical and not clinical_numbers(text)
