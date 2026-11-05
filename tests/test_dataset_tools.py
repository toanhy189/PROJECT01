"""Kiểm tra bộ lọc và số đếm từ CSV thật, không gán tỷ lệ khảo sát cho cá nhân."""

import json

import pytest
from pydantic import ValidationError

from backend.core.config import get_settings
from backend.ml.dataset_service import query_dataset
from backend.schemas.tools import DatasetQuery


def test_dataset_counts_match_cleaning_report():
    """Toàn miền trả đúng số dòng đã loại trùng và tổng hai nhãn bằng tổng mẫu."""
    settings = get_settings()
    result = query_dataset(DatasetQuery(), settings.artifact_dir)
    report = json.loads((settings.artifact_dir / "data_report.json").read_text("utf-8"))
    assert result["count"] == report["rows_after_deduplication"]
    assert result["class_0"] + result["class_1"] == result["count"]
    assert result["class_1_fraction"] == pytest.approx(result["class_1"] / result["count"])
    assert "cá nhân" in result["limitations"]


def test_filters_partition_bmi_range():
    """Hai khoảng không giao nhau tạo đúng toàn miền; không đếm trùng hàng."""
    directory = get_settings().artifact_dir
    total = query_dataset(DatasetQuery(), directory)
    low = query_dataset(DatasetQuery(bmi_max=24), directory)
    high = query_dataset(DatasetQuery(bmi_min=25), directory)
    assert low["count"] + high["count"] == total["count"]
    for label in ("class_0", "class_1"):
        assert low[label] + high[label] == total[label]


def test_invalid_range_and_arbitrary_sql_rejected():
    """Không chấp nhận khoảng ngược hoặc mã truy vấn tự do."""
    with pytest.raises(ValueError):
        query_dataset(DatasetQuery(bmi_min=50, bmi_max=20), get_settings().artifact_dir)
    with pytest.raises(ValidationError):
        DatasetQuery(sql="SELECT * FROM data")
