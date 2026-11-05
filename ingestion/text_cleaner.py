"""Làm sạch văn bản mà vẫn giữ số liệu, đơn vị và ranh giới đoạn."""

import re
import unicodedata


def clean_text(text: str) -> str:
    """Giữ đoạn, số và đơn vị; chỉ chuẩn hóa ký tự và khoảng trắng."""
    text = unicodedata.normalize("NFC", text).replace("\x00", "")
    lines = [re.sub(r"[^\S\n]+", " ", line).strip() for line in text.splitlines()]
    return re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip()
