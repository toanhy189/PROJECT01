"""Nạp artifact đã huấn luyện và phân loại trên CPU theo đúng schema."""

import json
import pickle
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import torch

from backend.core.errors import ServiceError
from backend.ml.model import DiabetesMLP
from backend.schemas.api import ModelInfo, PredictionResult
from backend.schemas.features import FEATURE_BOUNDS, FEATURE_NAMES, PatientFeatures


class Predictor:
    """Quản lý model, scaler, ngưỡng và phiên bản trong cùng process suy luận."""

    def __init__(self, artifact_dir: Path) -> None:
        """Ghi thư mục artifact; trì hoãn nạp model đến khi thật sự cần."""
        self.artifact_dir = artifact_dir
        self.model: DiabetesMLP | None = None
        self.scaler = None
        self.threshold = 0.5
        self.version: str | None = None

    def load(self) -> None:
        """Nạp một lần sau khi kiểm tra thứ tự features, miền mã và version artifact."""
        if self.model is not None:
            return
        required = [
            "model.pt",
            "preprocessor.joblib",
            "feature_schema.json",
            "threshold.json",
            "training_config.json",
        ]
        if not all((self.artifact_dir / name).is_file() for name in required):
            raise ServiceError(
                "Chưa có model đã huấn luyện. Hãy chạy python -m training.train.", "model_missing"
            )
        try:
            schema = json.loads(
                (self.artifact_dir / "feature_schema.json").read_text(encoding="utf-8")
            )
            threshold = json.loads(
                (self.artifact_dir / "threshold.json").read_text(encoding="utf-8")
            )
            config = json.loads(
                (self.artifact_dir / "training_config.json").read_text(encoding="utf-8")
            )
            if schema["feature_names"] != FEATURE_NAMES:
                raise ValueError("Sai thứ tự đặc trưng")
            if schema["bounds"] != {name: list(bounds) for name, bounds in FEATURE_BOUNDS.items()}:
                raise ValueError("Miền đặc trưng không tương thích")
            if not (
                schema["model_version"] == threshold["model_version"] == config["model_version"]
            ):
                raise ValueError("Artifacts không cùng phiên bản")
            decision_threshold = float(threshold["threshold"])
            if not 0 <= decision_threshold <= 1:
                raise ValueError("Ngưỡng không hợp lệ")
            scaler = joblib.load(self.artifact_dir / "preprocessor.joblib")
            if list(scaler.feature_names_in_) != FEATURE_NAMES:
                raise ValueError("Preprocessor không tương thích")
            model = DiabetesMLP()
            # Chỉ nạp trọng số lên CPU, không yêu cầu GPU hoặc checkpoint chứa cả model.
            model.load_state_dict(
                torch.load(self.artifact_dir / "model.pt", map_location="cpu", weights_only=True)
            )
            model.eval()
        except (
            OSError,
            ValueError,
            KeyError,
            RuntimeError,
            EOFError,
            AttributeError,
            TypeError,
            pickle.UnpicklingError,
        ) as exc:
            raise ServiceError(
                "Model artifact bị lỗi hoặc không tương thích; hãy huấn luyện lại.", "model_invalid"
            ) from exc
        self.model, self.scaler = model, scaler
        self.threshold, self.version = decision_threshold, config["model_version"]

    def predict(self, features: PatientFeatures) -> PredictionResult:
        """Chuẩn hóa đúng thứ tự, chạy PyTorch và áp dụng ngưỡng từ validation."""
        self.load()
        frame = pd.DataFrame([features.model_dump()], columns=FEATURE_NAMES)
        # Giữ đúng thứ tự cột đã train; thứ tự key trong payload không quyết định đầu vào.
        inputs = self.scaler.transform(frame).astype(np.float32)
        if inputs.shape != (1, 21) or not np.isfinite(inputs).all():
            raise ServiceError("Dữ liệu sau chuẩn hóa không hợp lệ.", "preprocessing_invalid")
        with torch.inference_mode():
            score = torch.sigmoid(self.model(torch.from_numpy(inputs))).item()
        if not np.isfinite(score):
            raise ServiceError("Mô hình trả về điểm không hợp lệ.", "prediction_invalid")
        return PredictionResult(
            model_score=score,
            predicted_class=int(score >= self.threshold),
            threshold=self.threshold,
            model_version=self.version,
        )

    def info(self) -> ModelInfo:
        """Trả trạng thái sẵn sàng và metadata mà không tạo dự đoán giả."""
        try:
            self.load()
        except ServiceError:
            return ModelInfo(ready=False, feature_names=FEATURE_NAMES)
        return ModelInfo(
            ready=True,
            model_version=self.version,
            threshold=self.threshold,
            feature_names=FEATURE_NAMES,
        )
