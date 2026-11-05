"""Đối chiếu ID, quote và số liệu; không thay thế đánh giá hỗ trợ ngữ nghĩa."""

import re

from backend.llm.llm_provider import GeneratedAnswer
from backend.schemas.api import Citation


def normalize(text: str) -> str:
    """Chuẩn hóa chữ thường và khoảng trắng để đối chiếu quote với văn bản nguồn."""
    # HTML có thể để dấu phẩy tách khỏi từ; khác khoảng trắng không làm đổi quote.
    return re.sub(r"\s+([,.;:!?])", r"\1", " ".join(text.casefold().split()))


def clinical_numbers(text: str) -> set[str]:
    """Lấy số liệu cần đối chiếu, bỏ số chỉ tên típ bệnh và ID citation."""
    text = re.sub(r"\[S\d+\]", "", text)
    # Típ 1/2 là tên nhóm bệnh, không phải một phép đo hoặc liều điều trị.
    text = re.sub(r"\b(?:típ|tuýp|loại|type)\s*[12]\b", "", text, flags=re.IGNORECASE)
    return {value.replace(",", ".") for value in re.findall(r"\b\d+(?:[.,]\d+)?\b", text)}


def validate_citations(answer: GeneratedAnswer, sources: list[Citation]) -> tuple[bool, str]:
    """Kiểm tra nguồn có trong evidence, quote khớp và số liệu có trong đoạn dẫn."""
    if answer.insufficient_evidence or not answer.claims:
        return False, "Chưa đủ bằng chứng để trả lời câu hỏi này."
    allowed = {source.citation_id: source for source in sources}
    # Chỉ ID trong context của request hiện tại mới được phép xuất hiện ở câu trả lời.
    for claim in answer.claims:
        if not claim.citation_ids or len(set(claim.citation_ids)) != len(claim.citation_ids):
            return False, "Trích dẫn thiếu hoặc trùng ID."
        if set(claim.supporting_quotes) != set(claim.citation_ids):
            return False, "Trích dẫn thiếu đoạn bằng chứng tương ứng."
        if re.search(r"https?://|www\.", claim.text):
            return False, "Câu trả lời chứa URL ngoài danh sách nguồn đã kiểm tra."
        inline = set(re.findall(r"\[(S\d+)\]", claim.text))
        if not inline.issubset(set(claim.citation_ids)):
            return False, "Nội dung dẫn ID không có trong danh sách trích dẫn."
        for citation_id in claim.citation_ids:
            if citation_id not in allowed:
                return False, "Câu trả lời chứa trích dẫn không có trong bằng chứng."
            quote = normalize(claim.supporting_quotes.get(citation_id, ""))
            # Quote phải khớp nguồn; kiểm tra này chưa chứng minh claim đúng về ngữ nghĩa.
            if len(quote) < 20 or quote not in normalize(allowed[citation_id].quote):
                return False, "Đoạn trích dẫn không khớp tài liệu nguồn."
        # Kiểm tra sơ bộ số liệu; vẫn cần người đánh giá ý nghĩa nhận định.
        claimed_numbers = clinical_numbers(claim.text)
        support = " ".join(claim.supporting_quotes.values())
        supported_numbers = clinical_numbers(support)
        if not claimed_numbers.issubset(supported_numbers):
            return False, "Số liệu trong câu trả lời chưa được đoạn trích hỗ trợ."
    return True, ""
