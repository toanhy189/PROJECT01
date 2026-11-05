"""Định nghĩa thứ tự và miền mã hóa 21 đặc trưng CDC dùng cho train và API."""

from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field

# strict=True từ chối chuỗi và bool dù chúng có thể được ép thành số 0/1.
Binary = Annotated[int, Field(strict=True, ge=0, le=1)]
Days = Annotated[int, Field(strict=True, ge=0, le=30)]

# Thứ tự này phải giống nhau khi train, lưu schema và suy luận từ payload.
FEATURE_NAMES = [
    "HighBP",
    "HighChol",
    "CholCheck",
    "BMI",
    "Smoker",
    "Stroke",
    "HeartDiseaseorAttack",
    "PhysActivity",
    "Fruits",
    "Veggies",
    "HvyAlcoholConsump",
    "AnyHealthcare",
    "NoDocbcCost",
    "GenHlth",
    "MentHlth",
    "PhysHlth",
    "DiffWalk",
    "Sex",
    "Age",
    "Education",
    "Income",
]


class PatientFeatures(BaseModel):
    """Kiểm tra đủ 21 trường, từ chối trường thừa và mã ngoài miền dữ liệu."""

    model_config = ConfigDict(extra="forbid")

    HighBP: Binary
    HighChol: Binary
    CholCheck: Binary
    BMI: Annotated[float, Field(strict=True, ge=12, le=98, allow_inf_nan=False)]
    Smoker: Binary
    Stroke: Binary
    HeartDiseaseorAttack: Binary
    PhysActivity: Binary
    Fruits: Binary
    Veggies: Binary
    HvyAlcoholConsump: Binary
    AnyHealthcare: Binary
    NoDocbcCost: Binary
    GenHlth: Annotated[int, Field(strict=True, ge=1, le=5)]
    MentHlth: Days
    PhysHlth: Days
    DiffWalk: Binary
    Sex: Binary
    Age: Annotated[int, Field(strict=True, ge=1, le=13)]
    Education: Annotated[int, Field(strict=True, ge=1, le=6)]
    Income: Annotated[int, Field(strict=True, ge=1, le=8)]


FEATURE_BOUNDS = {name: (0, 1) for name in FEATURE_NAMES}
FEATURE_BOUNDS.update(
    {
        "BMI": (12, 98),
        "GenHlth": (1, 5),
        "MentHlth": (0, 30),
        "PhysHlth": (0, 30),
        "Age": (1, 13),
        "Education": (1, 6),
        "Income": (1, 8),
    }
)
