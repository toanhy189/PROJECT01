"""Xác thực dữ liệu, chia tập tránh rò rỉ và chuẩn hóa từ tập train."""

from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import StandardScaler

from backend.schemas.features import FEATURE_BOUNDS, FEATURE_NAMES

TARGET = "Diabetes_binary"


def load_dataset(path: Path) -> tuple[pd.DataFrame, dict]:
    """Đọc và kiểm tra dữ liệu trước khi loại bản ghi trùng hoàn toàn."""
    frame = pd.read_csv(path)
    # UCI có thể bổ sung cột định danh, không dùng cột này để huấn luyện.
    if "ID" in frame.columns:
        frame = frame.drop(columns="ID")
    expected = set(FEATURE_NAMES + [TARGET])
    if set(frame.columns) != expected:
        raise ValueError(f"Schema CSV không đúng. Cần các cột: {sorted(expected)}")
    if frame.empty or frame.isna().any().any():
        raise ValueError("CSV rỗng hoặc có giá trị thiếu; cần kiểm tra dữ liệu nguồn.")
    for name, (lower, upper) in {**FEATURE_BOUNDS, TARGET: (0, 1)}.items():
        # CSV có thể lưu mã nguyên dưới dạng float; kiểm tra giá trị thay vì chỉ dtype.
        values = pd.to_numeric(frame[name], errors="raise")
        if not np.isfinite(values).all() or not values.between(lower, upper).all():
            raise ValueError(f"Giá trị ngoài miền được mã hóa: {name}")
        if not np.equal(values, np.floor(values)).all():
            raise ValueError(f"CDC yêu cầu giá trị nguyên ở cột {name}")
    if set(frame[TARGET].unique()) != {0, 1}:
        raise ValueError("CSV phải chứa cả hai lớp 0 và 1.")
    report = {
        "rows_raw": len(frame),
        "columns": list(frame.columns),
        "dtypes": {name: str(dtype) for name, dtype in frame.dtypes.items()},
        "missing_values": frame.isna().sum().to_dict(),
        "duplicates_removed": int(frame.duplicated().sum()),
        "class_counts_raw": frame[TARGET].value_counts().sort_index().to_dict(),
        "feature_ranges": {
            name: {"min": float(frame[name].min()), "max": float(frame[name].max())}
            for name in FEATURE_NAMES
        },
        "label_definition": {
            "0": "Không tiểu đường theo nhãn khảo sát",
            "1": "Tiền tiểu đường hoặc tiểu đường theo nhãn khảo sát",
        },
    }
    frame = frame.drop_duplicates().reset_index(drop=True)
    report["rows_after_deduplication"] = len(frame)
    return frame[FEATURE_NAMES + [TARGET]], report


def split_data(frame: pd.DataFrame, seed: int = 42) -> tuple:
    """Giữ cùng bộ đặc trưng ở một tập để tránh rò rỉ giữa các tập."""
    # Các hàng có cùng đặc trưng nhưng nhãn khác nhau vẫn thuộc cùng một nhóm.
    groups = frame.groupby(FEATURE_NAMES, sort=False, dropna=False)[TARGET].max().reset_index()
    # Chia theo nhóm trước, rồi mới ghép lại các hàng để không làm rò rỉ features.
    train_groups, rest = train_test_split(
        groups,
        test_size=0.3,
        stratify=groups[TARGET],
        random_state=seed,
    )
    val_groups, test_groups = train_test_split(
        # Một nửa của phần 30% tạo validation, nửa còn lại giữ riêng làm test.
        rest,
        test_size=0.5,
        stratify=rest[TARGET],
        random_state=seed,
    )
    parts = [
        frame.merge(part[FEATURE_NAMES], on=FEATURE_NAMES, how="inner")
        for part in (train_groups, val_groups, test_groups)
    ]
    return tuple(parts)


def fit_preprocessor(train: pd.DataFrame) -> StandardScaler:
    """Học trung bình và độ lệch chuẩn chỉ từ 21 đặc trưng của tập train."""
    return StandardScaler().fit(train[FEATURE_NAMES])
