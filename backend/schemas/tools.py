"""Hợp đồng cho các công cụ mô hình và thống kê, không yêu cầu Gemini."""

from typing import Annotated, Literal

from pydantic import Field, field_validator

from backend.schemas.api import StrictModel
from backend.schemas.features import FEATURE_NAMES, PatientFeatures


class ScenarioRequest(StrictModel):
    """Giữ hồ sơ gốc và chỉ áp dụng những trường được yêu cầu thử."""

    patient_features: PatientFeatures
    changes: dict[str, Annotated[float, Field(strict=True, allow_inf_nan=False)]] = Field(
        min_length=1, max_length=21
    )

    @field_validator("changes")
    @classmethod
    def known_fields(cls, value: dict[str, float]) -> dict[str, float]:
        """Không cho thay nhãn hoặc trường ngoài bộ đặc trưng khảo sát."""
        if not set(value).issubset(FEATURE_NAMES):
            raise ValueError("Trường thay đổi không thuộc 21 đặc trưng.")
        return value


class DatasetQuery(StrictModel):
    """Bộ lọc cố định, không nhận câu SQL hoặc mã do người dùng cung cấp."""

    age_group: Annotated[int, Field(strict=True, ge=1, le=13)] | None = None
    bmi_min: Annotated[float, Field(ge=12, le=98, allow_inf_nan=False)] = 12
    bmi_max: Annotated[float, Field(ge=12, le=98, allow_inf_nan=False)] = 98
    sex: Literal[0, 1] | None = None
