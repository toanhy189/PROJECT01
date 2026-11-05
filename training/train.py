"""Huấn luyện baseline và MLP trên cùng phép chia, rồi lưu bộ artifact tương ứng."""

import argparse
import copy
import hashlib
import json
import random
from datetime import UTC, datetime
from pathlib import Path

import joblib
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import sklearn
import torch
from sklearn.calibration import calibration_curve
from sklearn.linear_model import LogisticRegression
from torch import nn
from torch.utils.data import DataLoader, TensorDataset

from backend.core.config import ROOT
from backend.ml.model import DiabetesMLP
from backend.schemas.api import LIMITATIONS
from backend.schemas.features import FEATURE_BOUNDS, FEATURE_NAMES
from training.eda import run_eda
from training.evaluate import choose_threshold, compute_metrics
from training.preprocess import TARGET, fit_preprocessor, load_dataset, split_data


def fit_mlp(
    x_train: np.ndarray,
    y_train: np.ndarray,
    x_val: np.ndarray,
    y_val: np.ndarray,
    epochs: int,
    batch_size: int,
    patience: int,
) -> tuple:
    """Huấn luyện theo batch, dừng sớm theo validation loss và khôi phục trọng số tốt nhất."""
    model = DiabetesMLP()
    # Trọng số lớp tính từ train để giảm ảnh hưởng mất cân bằng, không đọc nhãn test.
    positive_weight = float((y_train == 0).sum() / (y_train == 1).sum())
    criterion = nn.BCEWithLogitsLoss(pos_weight=torch.tensor([positive_weight]))
    optimizer = torch.optim.Adam(model.parameters(), lr=0.001)
    loader = DataLoader(
        TensorDataset(torch.from_numpy(x_train), torch.from_numpy(y_train)),
        batch_size=batch_size,
        shuffle=True,
    )
    val_x, val_y = torch.from_numpy(x_val), torch.from_numpy(y_val)
    best_loss, stale, history = float("inf"), 0, []
    best_weights = copy.deepcopy(model.state_dict())
    for epoch in range(epochs):
        model.train()
        total_loss = 0.0
        for features, labels in loader:
            optimizer.zero_grad()
            # Loss nhận logits trực tiếp; sigmoid ở đây sẽ làm sai BCEWithLogitsLoss.
            loss = criterion(model(features).squeeze(1), labels)
            loss.backward()
            optimizer.step()
            total_loss += loss.item() * len(features)
        # Tắt dropout và gradient khi đo validation; không cập nhật trọng số ở bước này.
        model.eval()
        with torch.inference_mode():
            val_loss = criterion(model(val_x).squeeze(1), val_y).item()
        history.append(
            {
                "epoch": epoch + 1,
                "train_loss": total_loss / len(x_train),
                "validation_loss": val_loss,
            }
        )
        print(
            f"Epoch {epoch + 1}: train={history[-1]['train_loss']:.4f}, val={val_loss:.4f}",
            flush=True,
        )
        if val_loss < best_loss - 1e-4:
            best_loss, stale = val_loss, 0
            # Sao chép độc lập để các epoch sau không làm thay đổi checkpoint tốt nhất.
            best_weights = copy.deepcopy(model.state_dict())
        else:
            stale += 1
            if stale >= patience:
                break
    model.load_state_dict(best_weights)
    model.eval()
    return model, history


def train(
    csv: Path,
    output: Path,
    epochs: int = 30,
    seed: int = 42,
    batch_size: int = 512,
    patience: int = 5,
) -> dict:
    """Chạy EDA, chia tập, huấn luyện hai mô hình và lưu kết quả test cùng cấu hình."""
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    torch.set_num_threads(4)
    torch.use_deterministic_algorithms(True)
    report = run_eda(csv, output)
    frame, _ = load_dataset(csv)
    train_frame, val_frame, test_frame = split_data(frame, seed)
    # Fit duy nhất trên train; validation và test chỉ dùng transform cùng scaler.
    scaler = fit_preprocessor(train_frame)
    x_train, x_val, x_test = [
        scaler.transform(part[FEATURE_NAMES]).astype(np.float32)
        for part in (train_frame, val_frame, test_frame)
    ]
    y_train, y_val, y_test = [
        part[TARGET].to_numpy(dtype=np.float32) for part in (train_frame, val_frame, test_frame)
    ]
    baseline = LogisticRegression(class_weight="balanced", max_iter=1000, random_state=seed)
    baseline.fit(x_train, y_train)
    baseline_threshold = choose_threshold(y_val, baseline.predict_proba(x_val)[:, 1])
    model, history = fit_mlp(x_train, y_train, x_val, y_val, epochs, batch_size, patience)
    with torch.inference_mode():
        val_scores = torch.sigmoid(model(torch.from_numpy(x_val))).squeeze(1).numpy()
        test_scores = torch.sigmoid(model(torch.from_numpy(x_test))).squeeze(1).numpy()
    threshold = choose_threshold(y_val, val_scores)
    # Test chỉ đo chất lượng sau khi mô hình và ngưỡng đã được chốt từ validation.
    metrics = {
        "logistic_regression": compute_metrics(
            y_test, baseline.predict_proba(x_test)[:, 1], baseline_threshold
        ),
        "mlp": compute_metrics(y_test, test_scores, threshold),
        "split_counts": {"train": len(y_train), "validation": len(y_val), "test": len(y_test)},
        "split_positive_rates": {
            name: float(labels.mean())
            for name, labels in (("train", y_train), ("validation", y_val), ("test", y_test))
        },
        "threshold_selection": "F1 tối đa trên validation; test giữ riêng",
        "deduplication": "Loại hàng trùng; cùng đặc trưng luôn thuộc cùng một tập",
        "limitations": LIMITATIONS,
    }
    version = datetime.now(UTC).strftime("cdc-mlp-%Y%m%dT%H%M%SZ")
    config = {
        "model_version": version,
        "seed": seed,
        "epochs_requested": epochs,
        "epochs_run": len(history),
        "batch_size": batch_size,
        "patience": patience,
        "optimizer": "Adam",
        "learning_rate": 0.001,
        "device": "cpu",
        "torch_version": torch.__version__,
        "sklearn_version": sklearn.__version__,
        "dataset_sha256": hashlib.sha256(csv.read_bytes()).hexdigest(),
        "rows_raw": report["rows_raw"],
        "history": history,
    }
    metrics["model_version"] = version
    metrics["dataset_sha256"] = config["dataset_sha256"]
    # Lưu cùng scaler, schema, ngưỡng và version để inference không trộn các lần train.
    torch.save(model.state_dict(), output / "model.pt")
    joblib.dump(scaler, output / "preprocessor.joblib")
    joblib.dump(baseline, output / "baseline.joblib")
    files = {
        "feature_schema.json": {
            "feature_names": FEATURE_NAMES,
            "bounds": FEATURE_BOUNDS,
            "model_version": version,
            "label_definition": report["label_definition"],
        },
        "threshold.json": {"threshold": threshold, "model_version": version},
        "metrics.json": metrics,
        "training_config.json": config,
    }
    for filename, value in files.items():
        (output / filename).write_text(
            json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    # Ràng buộc baseline và MLP với đúng bộ scaler/metrics của lần train này.
    manifest = {
        "model_version": version,
        "dataset_sha256": config["dataset_sha256"],
        "files": {
            name: hashlib.sha256((output / name).read_bytes()).hexdigest()
            for name in ("model.pt", "baseline.joblib", "preprocessor.joblib", "metrics.json")
        },
    }
    (output / "model_manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    true_fraction, mean_scores = calibration_curve(y_test, test_scores, n_bins=10)
    plt.plot(mean_scores, true_fraction, "o-", label="MLP chưa hiệu chuẩn")
    plt.plot([0, 1], [0, 1], "--", label="Tham chiếu")
    plt.xlabel("Điểm mô hình trung bình")
    plt.ylabel("Tỷ lệ lớp 1 quan sát")
    plt.legend()
    plt.tight_layout()
    plt.savefig(output / "calibration.png", dpi=120)
    plt.close("all")
    return metrics


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Huấn luyện MLP và Logistic Regression trên CPU")
    parser.add_argument(
        "--csv",
        type=Path,
        default=ROOT / "data/raw/diabetes_binary_health_indicators_BRFSS2015.csv",
    )
    parser.add_argument("--output", type=Path, default=ROOT / "artifacts")
    parser.add_argument("--epochs", type=int, default=30)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--batch-size", type=int, default=512)
    parser.add_argument("--patience", type=int, default=5)
    args = parser.parse_args()
    if min(args.epochs, args.batch_size, args.patience) < 1:
        parser.error("Số epoch, batch size và patience phải dương.")
    print(
        json.dumps(
            train(args.csv, args.output, args.epochs, args.seed, args.batch_size, args.patience),
            ensure_ascii=False,
            indent=2,
        )
    )
