"""Kiểm thử mã hóa features, chuẩn hóa và phép chia dữ liệu tránh rò rỉ."""

import numpy as np
import pandas as pd
import pytest
from pydantic import ValidationError

from backend.schemas.features import FEATURE_NAMES, PatientFeatures
from training.preprocess import fit_preprocessor, load_dataset, split_data


@pytest.fixture
def feature_dict():
    """Cung cấp input minh họa hợp lệ, không phải dữ liệu CDC để đo mô hình."""
    return {
        "HighBP": 0,
        "HighChol": 0,
        "CholCheck": 1,
        "BMI": 25.0,
        "Smoker": 0,
        "Stroke": 0,
        "HeartDiseaseorAttack": 0,
        "PhysActivity": 1,
        "Fruits": 1,
        "Veggies": 1,
        "HvyAlcoholConsump": 0,
        "AnyHealthcare": 1,
        "NoDocbcCost": 0,
        "GenHlth": 2,
        "MentHlth": 0,
        "PhysHlth": 0,
        "DiffWalk": 0,
        "Sex": 0,
        "Age": 5,
        "Education": 5,
        "Income": 6,
    }


@pytest.mark.parametrize(
    "field,value",
    [
        ("Age", 45),
        ("Income", 9),
        ("Sex", True),
        ("BMI", float("nan")),
        ("HighBP", "1"),
        ("MentHlth", 31),
    ],
)
def test_reject_invalid_encoding(feature_dict, field, value):
    """Từ chối mã sai miền, sai kiểu và số không hữu hạn ở từng trường."""
    feature_dict[field] = value
    with pytest.raises(ValidationError):
        PatientFeatures(**feature_dict)


def test_missing_and_extra_features(feature_dict):
    """Input phải có đúng 21 trường, không thiếu hoặc thừa."""
    feature_dict.pop("BMI")
    with pytest.raises(ValidationError):
        PatientFeatures(**feature_dict)
    feature_dict["BMI"] = 25.0
    feature_dict["extra"] = 1
    with pytest.raises(ValidationError):
        PatientFeatures(**feature_dict)


def test_scaler_does_not_fit_validation(feature_dict):
    """Transform input mới không được thay đổi thống kê scaler đã fit trên train."""
    train = pd.DataFrame([feature_dict, {**feature_dict, "BMI": 30.0}])
    scaler = fit_preprocessor(train)
    before = scaler.mean_.copy()
    transformed = scaler.transform(pd.DataFrame([{**feature_dict, "BMI": 98.0}])[FEATURE_NAMES])
    assert transformed.shape == (1, 21)
    np.testing.assert_array_equal(before, scaler.mean_)


def test_bad_csv_schema(tmp_path):
    """CSV thiếu các cột bắt buộc phải bị từ chối trước huấn luyện."""
    path = tmp_path / "bad.csv"
    path.write_text("Age,Diabetes_binary\n5,0\n", encoding="utf-8")
    with pytest.raises(ValueError, match="Schema"):
        load_dataset(path)


def test_group_split_no_leakage(feature_dict):
    """Các hàng có cùng features không được xuất hiện ở nhiều tập dữ liệu."""
    rows = [
        {**feature_dict, "BMI": 12 + i % 80, "Age": 1 + i // 80, "Diabetes_binary": i % 2}
        for i in range(320)
    ]
    rows.append({**rows[0], "Diabetes_binary": 1})
    parts = split_data(pd.DataFrame(rows))
    keys = [set(map(tuple, part[FEATURE_NAMES].to_numpy())) for part in parts]
    assert not (keys[0] & keys[1] or keys[0] & keys[2] or keys[1] & keys[2])
