"""Kiểm tra CSV và xuất thống kê, biểu đồ phân bố trước huấn luyện."""

import argparse
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

from backend.core.config import ROOT
from backend.schemas.features import FEATURE_NAMES
from training.preprocess import TARGET, load_dataset


def run_eda(csv: Path, output: Path) -> dict:
    """Lưu báo cáo dữ liệu cùng biểu đồ đặc trưng và phân bố hai lớp."""
    frame, report = load_dataset(csv)
    output.mkdir(parents=True, exist_ok=True)
    report["summary"] = frame.describe().to_dict()
    (output / "data_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    frame[FEATURE_NAMES].hist(figsize=(16, 12), bins=15)
    plt.suptitle("Phân bố 21 đặc trưng CDC")
    plt.tight_layout()
    plt.savefig(output / "feature_distributions.png", dpi=120)
    plt.close("all")
    frame[TARGET].value_counts().sort_index().plot.bar(title="Phân bố nhãn sau loại trùng")
    plt.tight_layout()
    plt.savefig(output / "target_distribution.png", dpi=120)
    plt.close("all")
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Kiểm tra dữ liệu và tạo biểu đồ EDA")
    parser.add_argument(
        "--csv",
        type=Path,
        default=ROOT / "data/raw/diabetes_binary_health_indicators_BRFSS2015.csv",
    )
    parser.add_argument("--output", type=Path, default=ROOT / "artifacts")
    args = parser.parse_args()
    report = run_eda(args.csv, args.output)
    print(json.dumps({k: v for k, v in report.items() if k != "summary"}, ensure_ascii=False))
