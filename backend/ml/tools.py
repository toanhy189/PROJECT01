"""Công cụ suy luận thật, mô phỏng và kiểm tra nguồn gốc của artifact."""

import hashlib
import json
import threading
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from pydantic import ValidationError

from backend.core.errors import ServiceError
from backend.ml.inference import Predictor
from backend.schemas.features import FEATURE_NAMES, PatientFeatures


def profile_hash(features: PatientFeatures) -> str:
    """Gắn kết quả với đúng giá trị đầu vào, không dùng làm mã định danh người."""
    raw = json.dumps(features.model_dump(), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode()).hexdigest()


class ModelTools:
    """Dùng cùng predictor, scaler và trọng số cho mọi phép so sánh."""

    def __init__(self, predictor: Predictor, artifact_dir: Path) -> None:
        """Giữ dịch vụ mô hình; chỉ nạp baseline khi người dùng yêu cầu."""
        self.predictor = predictor
        self.artifact_dir = artifact_dir
        self._baseline = None
        self._lock = threading.Lock()

    def scenario(self, features: PatientFeatures, changes: dict[str, float]) -> dict:
        """Tạo bản thử mới, tuyệt đối không sửa đối tượng hồ sơ gốc."""
        values = features.model_dump()
        for key, value in changes.items():
            if key not in FEATURE_NAMES or not np.isfinite(value):
                raise ValueError("Trường hoặc giá trị thay đổi không hợp lệ.")
            if key != "BMI":
                if not float(value).is_integer():
                    raise ValueError("Đặc trưng mã hóa phải là số nguyên.")
                value = int(value)
            values[key] = value
        try:
            modified = PatientFeatures(**values)
        except ValidationError as exc:
            raise ValueError("Giá trị bản thử nằm ngoài miền của đặc trưng.") from exc
        before = self.predictor.predict(features)
        after = self.predictor.predict(modified)
        return {
            "before": before.model_dump(),
            "after": after.model_dump(),
            "score_delta": after.model_score - before.model_score,
            "changes": {
                key: {"before": getattr(features, key), "after": getattr(modified, key)}
                for key in changes
            },
            "original_hash": profile_hash(features),
            "modified_hash": profile_hash(modified),
            "modified_features": modified.model_dump(),
            "interpretation": (
                "Thử độ nhạy của mô hình; không biểu thị hiệu quả điều trị "
                "hoặc mức giảm nguy cơ bệnh."
            ),
        }

    def compare(self, features: PatientFeatures) -> dict:
        """So sánh hai model, giữ kết quả đã có nếu một artifact không nạp được."""
        results, errors = [], []
        try:
            result = self.predictor.predict(features)
            results.append({"model_name": "PyTorch MLP", **result.model_dump()})
        except ServiceError as exc:
            errors.append({"model_name": "PyTorch MLP", "code": exc.code, "message": str(exc)})
        try:
            self.predictor.load()
            manifest = json.loads((self.artifact_dir / "model_manifest.json").read_text("utf-8"))
            if manifest["model_version"] != self.predictor.version:
                raise ValueError("Artifact không cùng phiên bản.")
            for filename, digest in manifest["files"].items():
                if filename not in {
                    "baseline.joblib",
                    "preprocessor.joblib",
                    "model.pt",
                    "metrics.json",
                }:
                    raise ValueError("Manifest chứa tên file không hợp lệ.")
                if (
                    hashlib.sha256((self.artifact_dir / filename).read_bytes()).hexdigest()
                    != digest
                ):
                    raise ValueError("Artifact đã đổi so với manifest.")
            if not {"baseline.joblib", "preprocessor.joblib", "model.pt", "metrics.json"}.issubset(
                manifest["files"]
            ):
                raise ValueError("Manifest thiếu dấu artifact.")
            with self._lock:
                if self._baseline is None:
                    self._baseline = joblib.load(self.artifact_dir / "baseline.joblib")
            frame = pd.DataFrame([features.model_dump()], columns=FEATURE_NAMES)
            values = self.predictor.scaler.transform(frame).astype(np.float32)
            index = list(self._baseline.classes_).index(1)
            score = float(self._baseline.predict_proba(values)[0, index])
            metrics = json.loads((self.artifact_dir / "metrics.json").read_text("utf-8"))
            if metrics["model_version"] != self.predictor.version:
                raise ValueError("Metrics không cùng phiên bản.")
            threshold = float(metrics["logistic_regression"]["threshold"])
            if not np.isfinite(score) or not 0 <= score <= 1 or not 0 <= threshold <= 1:
                raise ValueError("Điểm hoặc ngưỡng không hợp lệ.")
            results.append(
                {
                    "model_name": "Logistic Regression",
                    "model_score": score,
                    "threshold": threshold,
                    "predicted_class": int(score >= threshold),
                    "model_version": self.predictor.version,
                }
            )
        except (OSError, ValueError, KeyError, AttributeError, ServiceError):
            errors.append(
                {
                    "model_name": "Logistic Regression",
                    "code": "baseline_unavailable",
                    "message": "Baseline chưa sẵn sàng hoặc không khớp bộ artifact đã xác minh.",
                }
            )
        return {
            "profile_hash": profile_hash(features),
            "models": results,
            "errors": errors,
            "agreement": len(results) == 2
            and results[0]["predicted_class"] == results[1]["predicted_class"],
        }

    def inspection(self) -> dict:
        """Chỉ công bố báo cáo ảnh hưởng thuộc đúng trọng số đang phục vụ."""
        self.predictor.load()
        try:
            report = json.loads(
                (self.artifact_dir / "ml_feature_importance.json").read_text("utf-8")
            )
            digest = hashlib.sha256((self.artifact_dir / "model.pt").read_bytes()).hexdigest()
            if (
                report["model_version"] != self.predictor.version
                or report.get("model_sha256") != digest
                or report.get("preprocessor_sha256")
                != hashlib.sha256(
                    (self.artifact_dir / "preprocessor.joblib").read_bytes()
                ).hexdigest()
            ):
                raise ValueError("Báo cáo thuộc model khác.")
            return report
        except (OSError, ValueError, KeyError) as exc:
            raise ServiceError(
                "Chưa có báo cáo ảnh hưởng khớp model hiện tại.", "inspection_unavailable"
            ) from exc
