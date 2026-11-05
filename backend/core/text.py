"""Chuẩn hóa tiếng Việt để đối chiếu quy tắc, không sửa nội dung nguồn."""

import unicodedata


def plain_text(text: str) -> str:
    """Bỏ dấu và chuyển chữ thường cho các mẫu nhận biết đầu vào."""
    text = unicodedata.normalize("NFD", text.casefold()).replace("đ", "d")
    return "".join(char for char in text if unicodedata.category(char) != "Mn")
