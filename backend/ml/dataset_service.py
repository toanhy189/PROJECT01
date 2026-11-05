"""Thống kê có giới hạn từ khảo sát CDC, tách khỏi dự đoán cá nhân."""

import hashlib
import json
from functools import lru_cache
from pathlib import Path

import pandas as pd

from backend.core.config import ROOT
from backend.core.errors import ServiceError
from backend.schemas.tools import DatasetQuery
from training.preprocess import TARGET, load_dataset


@lru_cache(maxsize=2)
def dataset_frame(path: str, modified_ns: int, size: int) -> tuple[pd.DataFrame, str]:
    """Đọc và loại trùng theo đúng pipeline; khóa cache thay khi file thay đổi."""
    source = Path(path)
    frame, _ = load_dataset(source)
    return frame, hashlib.sha256(source.read_bytes()).hexdigest()


def query_dataset(query: DatasetQuery, artifact_dir: Path) -> dict:
    """Lọc theo mã tuổi, giới tính và khoảng BMI; không nhận SQL tự do."""
    if query.bmi_min > query.bmi_max:
        raise ValueError("BMI tối thiểu không được lớn hơn tối đa.")
    try:
        path = ROOT / "data/raw/diabetes_binary_health_indicators_BRFSS2015.csv"
        stat = path.stat()
        frame, digest = dataset_frame(str(path), stat.st_mtime_ns, stat.st_size)
        config = json.loads((artifact_dir / "training_config.json").read_text("utf-8"))
        if digest != config["dataset_sha256"]:
            raise ValueError("Dữ liệu không cùng phiên bản huấn luyện.")
    except (OSError, ValueError, KeyError) as exc:
        raise ServiceError(
            "Dữ liệu khảo sát chưa sẵn sàng hoặc đã thay đổi.", "dataset_unavailable"
        ) from exc
    mask = frame.BMI.between(query.bmi_min, query.bmi_max)
    if query.age_group is not None:
        mask &= frame.Age == query.age_group
    if query.sex is not None:
        mask &= frame.Sex == query.sex
    selected = frame.loc[mask, TARGET]
    return {
        "filters": query.model_dump(),
        "count": len(selected),
        "class_0": int((selected == 0).sum()),
        "class_1": int((selected == 1).sum()),
        "class_1_fraction": float(selected.mean()) if len(selected) else None,
        "total_clean_rows": len(frame),
        "dataset_sha256": digest,
        "source": "UCI CDC BRFSS 2015",
        "source_url": "https://archive.ics.uci.edu/dataset/891/cdc-diabetes-health-indicators",
        "limitations": (
            "Nhãn khảo sát sau loại trùng; tỷ lệ nhóm không phải xác suất mắc bệnh của cá nhân."
        ),
    }
