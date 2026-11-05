"""Nhận thông số BMI rõ ràng; không đoán giá trị thiếu hoặc trộn nhiều người."""

import re
from dataclasses import dataclass

from backend.core.text import plain_text
from backend.schemas.features import PatientFeatures

BMI_VALUE = re.compile(
    r"\bbmi\s*(?:(?:cua\s+(?:minh|mik|toi|em|ban|con)\s*)?(?:la|bang)?\s*[:=]?\s*)"
    r"(-?\d+(?:[.,]\d+)?)\b"
)


@dataclass(frozen=True)
class BmiInput:
    """Giữ nguồn gốc giá trị và phạm vi, không xác nhận đó là phép đo thật."""

    value: float | None
    origin: str
    adult: bool | None
    reason: str = ""


def bmi_input(question: str, features: PatientFeatures | None = None) -> BmiInput | None:
    """Chỉ lấy số có nhãn BMI; bỏ qua câu yêu cầu thay đổi để nhánh mô phỏng xử lý."""
    text = plain_text(question)
    if "bmi" not in text or re.search(r"\b(?:giam|tang|doi|thay)\b", text):
        return None
    values = [float(match.group(1).replace(",", ".")) for match in BMI_VALUE.finditer(text)]
    # Không suy diễn một mốc đang được hỏi thành chỉ số cá nhân.
    if not values and not (features and re.search(r"cao|thap|binh thuong|danh gia|beo|cua", text)):
        return None
    if len(values) > 1 or re.search(r"ban toi|ban minh|ban mik|con toi|con minh|nguoi khac", text):
        return BmiInput(
            None,
            "question",
            None,
            "Bạn đang hỏi cho nhiều người hoặc một người khác. "
            "Hãy nêu rõ một chỉ số và độ tuổi cần xét; hồ sơ trong form được giữ nguyên.",
        )
    value = values[0] if values else features.BMI
    if not 0 < value <= 200:
        return BmiInput(
            None,
            "question",
            None,
            "Chỉ số BMI chưa hợp lý để đối chiếu. Hãy kiểm tra lại giá trị BMI và đơn vị; "
            "không nhập cân nặng thay BMI.",
        )
    if features and values and abs(value - features.BMI) > 1e-6:
        return BmiInput(
            value,
            "question",
            None,
            f"Câu hỏi ghi BMI {value:g}, còn form ghi BMI {features.BMI:g}. "
            "Hãy xác nhận giá trị cần xét; hệ thống chưa thay đổi hồ sơ gốc.",
        )
    ages = re.findall(r"\b(\d{1,3})\s*tuoi\b", text)
    adult = (
        int(ages[0]) >= 20 if len(ages) == 1 else (True if features and features.Age >= 2 else None)
    )
    if len(ages) > 1:
        return BmiInput(
            value,
            "question",
            None,
            "Có nhiều độ tuổi trong câu hỏi. Hãy xác nhận tuổi của người có chỉ số BMI đang xét.",
        )
    scope_text = text.replace("khong mang thai", "").replace("khong co thai", "")
    if re.search(r"mang thai|co thai|thai ky|ba bau|dang bau|co bau", scope_text):
        return BmiInput(
            value,
            "question",
            False,
            "Chưa áp dụng bảng BMI người lớn cho ngữ cảnh thai kỳ. "
            "Bạn cần đánh giá cân nặng theo tình trạng cụ thể với nhân viên y tế.",
        )
    return BmiInput(value, "question" if values else "form", adult)


def scenario_change(question: str, focus: str | None = None) -> tuple[float | None, bool]:
    """Nhận yêu cầu BMI tăng/giảm rõ ràng; câu nối tiếp cần trọng tâm đã xác định."""
    text = plain_text(question)
    match = re.search(r"\b(giam|tang)\s+(-?\d+(?:[.,]\d+)?)\b", text)
    if not match:
        return None, False
    if "bmi" not in text and focus != "BMI":
        return None, True
    value = float(match.group(2).replace(",", "."))
    if value <= 0 or re.search(r"\b(?:kg|mg|cm|vien)\b", text):
        return None, True
    return (-value if match.group(1) == "giam" else value), False
