"""Kiểm thử lỗi artifact và suy luận HTTP bằng model CDC đã huấn luyện thật."""

import json
import shutil

import numpy as np
import pandas as pd
import pytest
import torch
from fastapi.testclient import TestClient

from backend.core.config import ROOT, Settings
from backend.core.errors import ServiceError
from backend.graph.workflow import Workflow, get_workflow
from backend.main import app
from backend.ml.inference import Predictor
from backend.schemas.features import FEATURE_NAMES, PatientFeatures


def test_missing_model_is_explicit(tmp_path):
    """Thiếu artifact phải báo chưa sẵn sàng và lỗi dịch vụ rõ ràng."""
    predictor = Predictor(tmp_path)
    assert not predictor.info().ready
    with pytest.raises(ServiceError, match="huấn luyện"):
        predictor.load()


@pytest.mark.parametrize("artifact", ["feature_schema.json", "preprocessor.joblib", "model.pt"])
def test_corrupt_artifact_is_service_error(tmp_path, artifact):
    """Schema, scaler hoặc checkpoint hỏng phải được chuyển thành lỗi model_invalid."""
    source = ROOT / "artifacts"
    if not (source / "model.pt").exists():
        pytest.skip("Cần artifact huấn luyện trước khi kiểm tra tệp hỏng.")
    for filename in (
        "model.pt",
        "preprocessor.joblib",
        "feature_schema.json",
        "threshold.json",
        "training_config.json",
    ):
        shutil.copy2(source / filename, tmp_path / filename)
    if artifact.endswith("json"):
        schema = json.loads((tmp_path / artifact).read_text(encoding="utf-8"))
        schema["bounds"]["Age"] = [1, 100]
        (tmp_path / artifact).write_text(json.dumps(schema), encoding="utf-8")
    elif artifact.endswith("joblib"):
        import joblib

        joblib.dump({"wrong": "preprocessor"}, tmp_path / artifact)
    else:
        (tmp_path / artifact).write_bytes(b"invalid checkpoint")
    with pytest.raises(ServiceError) as error:
        Predictor(tmp_path).load()
    assert error.value.code == "model_invalid"


def test_real_artifacts_inference_and_http(feature_dict):
    """Đối chiếu điểm từ artifact với API và kiểm tra fallback khi thiếu Gemini key."""
    if not (ROOT / "artifacts/model.pt").exists():
        pytest.skip("Cần huấn luyện dữ liệu CDC thật trước khi chạy kiểm thử artifact.")
    predictor = Predictor(ROOT / "artifacts")
    features = PatientFeatures(**feature_dict)
    result = predictor.predict(features)
    config = json.loads((ROOT / "artifacts/training_config.json").read_text(encoding="utf-8"))
    assert config["rows_raw"] == 253680
    assert len(config["dataset_sha256"]) == 64
    assert result.model_version == config["model_version"]
    assert result.predicted_class == int(result.model_score >= result.threshold)
    # So sánh suy luận dịch vụ với preprocessor và PyTorch artifact trực tiếp.
    inputs = predictor.scaler.transform(pd.DataFrame([feature_dict], columns=FEATURE_NAMES)).astype(
        np.float32
    )
    with torch.inference_mode():
        direct_score = torch.sigmoid(predictor.model(torch.from_numpy(inputs))).item()
    assert result.model_score == pytest.approx(direct_score)
    workflow = Workflow(Settings(gemini_api_key=""), predictor=predictor)
    app.dependency_overrides[get_workflow] = lambda: workflow
    try:
        client = TestClient(app)
        assert client.get("/api/v1/model-info").json()["ready"]
        predicted = client.post("/api/v1/predict", json={"patient_features": feature_dict})
        assert predicted.status_code == 200
        assert predicted.json()["model_score"] == pytest.approx(direct_score)
        response = client.post("/api/v1/analyze", json={"patient_features": feature_dict})
        assert response.status_code == 200
        data = response.json()
        assert data["safety_status"] == "passed"
        assert [entry["agent"] for entry in data["agent_trace"]] == [
            "Coordinator",
            "Prediction Agent",
            "Safety Agent",
        ]
        fallback = client.post("/api/v1/chat", json={"user_query": "Tiểu đường là gì?"})
        assert fallback.status_code == 200
        assert fallback.json()["safety_status"] == "fallback"
        assert "GEMINI_API_KEY" in fallback.json()["generated_answer"]
        assert not fallback.json()["citations"]
    finally:
        app.dependency_overrides.clear()
