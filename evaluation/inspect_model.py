"""Đo mức phụ thuộc đặc trưng của model đã lưu, không huấn luyện lại."""

import argparse
import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import torch
from sklearn.metrics import roc_auc_score

from backend.core.config import ROOT, get_settings
from backend.ml.inference import Predictor
from backend.schemas.features import FEATURE_NAMES
from training.preprocess import TARGET, load_dataset, split_data


def inspect_model(csv: Path, artifact_dir: Path, repeats: int = 5) -> dict:
    """Xáo trộn từng cột trên tập test gốc, giữ nguyên trọng số và ngưỡng."""
    if not 1 <= repeats <= 20:
        raise ValueError("Số lần xáo trộn phải trong khoảng 1–20.")
    config = json.loads((artifact_dir / "training_config.json").read_text("utf-8"))
    metrics = json.loads((artifact_dir / "metrics.json").read_text("utf-8"))
    digest = hashlib.sha256(csv.read_bytes()).hexdigest()
    if digest != config["dataset_sha256"] or metrics["model_version"] != config["model_version"]:
        raise ValueError("Dữ liệu, model và metrics không cùng phiên bản.")
    frame, _ = load_dataset(csv)
    _, _, test = split_data(frame, config["seed"])
    if len(test) != metrics["split_counts"]["test"]:
        raise ValueError("Phép chia không khớp tập test đã lưu.")
    predictor = Predictor(artifact_dir)
    predictor.load()
    values = predictor.scaler.transform(test[FEATURE_NAMES]).astype(np.float32)
    labels = test[TARGET].to_numpy(dtype=np.float32)

    def scores(matrix: np.ndarray) -> np.ndarray:
        """Tắt dropout và gradient; chỉ lấy điểm của model đang phục vụ."""
        with torch.inference_mode():
            return torch.sigmoid(predictor.model(torch.from_numpy(matrix))).squeeze(1).numpy()

    baseline = float(roc_auc_score(labels, scores(values)))
    if abs(baseline - metrics["mlp"]["roc_auc"]) > 1e-6:
        raise ValueError("Model không tái lập ROC-AUC đã lưu; chưa công bố báo cáo.")
    results = []
    for column, feature in enumerate(FEATURE_NAMES):
        rng = np.random.default_rng(42)
        measured = []
        for _ in range(repeats):
            permuted = values.copy()
            permuted[:, column] = values[rng.permutation(len(values)), column]
            measured.append(float(roc_auc_score(labels, scores(permuted))))
        drops = baseline - np.asarray(measured)
        results.append(
            {
                "feature": feature,
                "mean_roc_auc_drop": float(drops.mean()),
                "shuffle_std": float(drops.std()),
                "permuted_roc_auc": measured,
            }
        )
    results.sort(key=lambda item: item["mean_roc_auc_drop"], reverse=True)
    for rank, item in enumerate(results, start=1):
        item["rank"] = rank
    return {
        "checked_at": datetime.now(UTC).isoformat(),
        "model_version": predictor.version,
        "model_sha256": hashlib.sha256((artifact_dir / "model.pt").read_bytes()).hexdigest(),
        "preprocessor_sha256": hashlib.sha256(
            (artifact_dir / "preprocessor.joblib").read_bytes()
        ).hexdigest(),
        "dataset_sha256": digest,
        "baseline_roc_auc": baseline,
        "test_rows": len(test),
        "repeats": repeats,
        "permutation_seed": 42,
        "split_seed": config["seed"],
        "method": "Single-feature permutation importance on the original held-out test split.",
        "metric": "ROC-AUC drop; larger positive drop indicates greater model dependence.",
        "baseline_matches_saved_metrics": True,
        "results": results,
        "limitations": [
            "Global model dependence, not a per-patient explanation or medical causal effect.",
            "Correlated features and unrealistic shuffled combinations can affect importance.",
            "Shuffle variation is not a population confidence interval.",
            (
                "Do not tune the model using this test analysis "
                "and reuse the test as independent evidence."
            ),
        ],
    }


def main() -> None:
    """Ghi báo cáo riêng, không thay đổi model, scaler, ngưỡng hoặc metrics."""
    parser = argparse.ArgumentParser(description="Đo ảnh hưởng chung của 21 đặc trưng")
    parser.add_argument("--repeats", type=int, default=5)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    settings = get_settings()
    torch.set_num_threads(4)
    report = inspect_model(
        ROOT / "data/raw/diabetes_binary_health_indicators_BRFSS2015.csv",
        settings.artifact_dir,
        args.repeats,
    )
    output = args.output or settings.artifact_dir / "ml_feature_importance.json"
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(
        json.dumps(
            {
                "output": str(output),
                "rows": report["test_rows"],
                "top_features": [item["feature"] for item in report["results"][:5]],
            }
        )
    )


if __name__ == "__main__":
    main()
