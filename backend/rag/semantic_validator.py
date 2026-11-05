"""Chặn một số lỗi tráo khoảng xét nghiệm; không thay thế đánh giá y khoa."""

import re

from backend.core.text import plain_text
from backend.llm.llm_provider import GeneratedAnswer


def validate_clinical_meaning(answer: GeneratedAnswer) -> tuple[bool, str]:
    """Không chấp nhận các khoảng tiền tiểu đường bị gọi thành chẩn đoán tiểu đường."""
    ranges = (
        r"5[.,]7\s*(?:%\s*)?(?:den|toi|[-–])\s*6[.,]4",
        r"100\s*(?:den|toi|[-–])\s*125",
        r"140\s*(?:den|toi|[-–])\s*199",
    )
    for claim in answer.claims:
        for sentence in re.split(r"[;\n]|\.(?!\d)", plain_text(claim.text)):
            if "tien tieu duong" in sentence or "prediabetes" in sentence:
                continue
            if re.search(
                r"chan doan.{0,30}tieu duong|tieu duong.{0,40}(?:a1c|huyet|glucose)", sentence
            ) and any(re.search(pattern, sentence) for pattern in ranges):
                return (
                    False,
                    (
                        "Phần diễn giải đang nhầm khoảng tiền tiểu đường với tiểu đường. "
                        "Câu trả lời chưa được chấp nhận; vui lòng đối chiếu bảng nguồn."
                    ),
                )
    return True, ""
