"""Kiểm thử công cụ mới bằng artifact thật; không gọi Gemini."""

import hashlib
import json
from shutil import copy2

import pytest
from fastapi.testclient import TestClient

from backend.core.config import get_settings
from backend.core.errors import ServiceError
from backend.graph.workflow import Workflow, get_workflow
from backend.main import app
from backend.ml.inference import Predictor
from backend.ml.tools import ModelTools, profile_hash
from backend.schemas.features import PatientFeatures


@pytest.fixture
def tools():
    """Dùng model đã lưu, không train lại hoặc thay đổi artifact."""
    settings = get_settings()
    return ModelTools(Predictor(settings.artifact_dir), settings.artifact_dir)


def test_scenario_preserves_original_and_matches_predictor(tools, feature_dict):
    """Một trường đổi, các trường khác và hồ sơ gốc được giữ nguyên."""
    features = PatientFeatures(**feature_dict)
    result = tools.scenario(features, {"BMI": 35})
    assert features.BMI == feature_dict["BMI"]
    assert result["original_hash"] == profile_hash(features)
    assert (
        result["after"]["model_score"]
        == tools.predictor.predict(features.model_copy(update={"BMI": 35.0})).model_score
    )
    assert {
        key for key in feature_dict if result["modified_features"][key] != feature_dict[key]
    } == {"BMI"}
    assert result["score_delta"] == pytest.approx(
        result["after"]["model_score"] - result["before"]["model_score"]
    )
    unchanged = tools.scenario(features, {"BMI": features.BMI})
    assert unchanged["score_delta"] == 0


@pytest.mark.parametrize("changes", [{"BMI": 100}, {"Age": 2.5}, {"Age": 0}, {"label": 1}])
def test_scenario_rejects_invalid_changes(tools, feature_dict, changes):
    """Không ép mã lẻ, thay nhãn hoặc cho vượt miền của model."""
    with pytest.raises(ValueError):
        tools.scenario(PatientFeatures(**feature_dict), changes)


def test_comparison_uses_separate_thresholds(tools, feature_dict):
    """Hai model dùng cùng hồ sơ nhưng có ngưỡng riêng từ metrics."""
    result = tools.compare(PatientFeatures(**feature_dict))
    assert result["errors"] == []
    assert len(result["models"]) == 2
    metrics = json.loads((tools.artifact_dir / "metrics.json").read_text("utf-8"))
    for name, metric in (("PyTorch MLP", "mlp"), ("Logistic Regression", "logistic_regression")):
        model = next(item for item in result["models"] if item["model_name"] == name)
        assert model["threshold"] == metrics[metric]["threshold"]
        assert model["predicted_class"] == int(model["model_score"] >= model["threshold"])


def test_corrupt_baseline_keeps_mlp_result(tmp_path, tools, feature_dict):
    """Lỗi baseline không làm mất kết quả MLP và không nạp pickle đã đổi."""
    for name in (
        "model.pt",
        "preprocessor.joblib",
        "feature_schema.json",
        "threshold.json",
        "training_config.json",
        "metrics.json",
        "model_manifest.json",
        "baseline.joblib",
    ):
        copy2(tools.artifact_dir / name, tmp_path / name)
    (tmp_path / "baseline.joblib").write_bytes(b"invalid")
    result = ModelTools(Predictor(tmp_path), tmp_path).compare(PatientFeatures(**feature_dict))
    assert len(result["models"]) == 1
    assert result["models"][0]["model_name"] == "PyTorch MLP"
    assert result["errors"][0]["code"] == "baseline_unavailable"


def test_inspection_is_bound_to_weights(tools, tmp_path):
    """Không dùng biểu đồ của model cũ cho trọng số khác."""
    result = tools.inspection()
    assert (
        result["model_sha256"]
        == hashlib.sha256((tools.artifact_dir / "model.pt").read_bytes()).hexdigest()
    )
    tools.artifact_dir = tmp_path
    with pytest.raises(ServiceError, match="báo cáo"):
        tools.inspection()


def test_tools_http_no_gemini(feature_dict):
    """Các công cụ ML thực sự chạy qua API mà không cần key Gemini."""
    workflow = Workflow(get_settings().model_copy(update={"gemini_api_key": ""}))
    app.dependency_overrides[get_workflow] = lambda: workflow
    try:
        client = TestClient(app)
        response = client.post(
            "/api/v1/scenarios", json={"patient_features": feature_dict, "changes": {"BMI": 30}}
        )
        assert response.status_code == 200
        assert (
            response.json()["before"]["model_version"] == response.json()["after"]["model_version"]
        )
        assert (
            client.post(
                "/api/v1/scenarios",
                json={"patient_features": feature_dict, "changes": {"BMI": 999}},
            ).status_code
            == 422
        )
        assert (
            client.post(
                "/api/v1/scenarios",
                json={"patient_features": feature_dict, "changes": {"Age": True}},
            ).status_code
            == 422
        )
        assert (
            client.post(
                "/api/v1/models/compare", json={"patient_features": feature_dict}
            ).status_code
            == 200
        )
        assert client.get("/api/v1/model-inspection").status_code == 200
    finally:
        app.dependency_overrides.clear()
