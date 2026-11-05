"""Kiểm thử routing LangGraph, trace, fallback và HTTP bằng dịch vụ mock."""

from unittest.mock import Mock

import pytest
from fastapi.testclient import TestClient

from backend.core.config import Settings
from backend.core.errors import ServiceError
from backend.graph.workflow import Workflow, get_workflow
from backend.llm.llm_provider import Claim, GeneratedAnswer
from backend.main import app
from backend.rag.retriever import Evidence
from backend.schemas.api import PredictionResult
from backend.schemas.features import PatientFeatures


@pytest.fixture
def services():
    """Tạo các dịch vụ mock có đầu ra biết trước, không gọi Gemini thật."""
    predictor, retriever, llm = Mock(), Mock(), Mock()
    predictor.predict.return_value = PredictionResult(
        model_score=0.3, predicted_class=0, threshold=0.5, model_version="test-only"
    )
    metadata = {
        "document_id": "test",
        "chunk_id": "chunk",
        "title": "Nguồn kiểm thử",
        "section": "Kiểm thử",
        "source_url": "https://www.niddk.nih.gov/health-information/diabetes",
    }
    retriever.retrieve.return_value = [
        Evidence("This evidence is used only for software validation.", metadata, 0.1)
    ]
    llm.generate.return_value = GeneratedAnswer(
        insufficient_evidence=False,
        claims=[
            Claim(
                text="Nội dung minh họa cho kiểm thử phần mềm.",
                citation_ids=["S1"],
                supporting_quotes={"S1": "This evidence is used only for software validation."},
            )
        ],
    )
    return predictor, retriever, llm


@pytest.mark.parametrize(
    "mode,expected",
    [
        ("prediction", ["Coordinator", "Prediction Agent", "Safety Agent"]),
        ("knowledge", ["Coordinator", "Knowledge Agent", "Consultation Agent", "Safety Agent"]),
        (
            "combined",
            [
                "Coordinator",
                "Prediction Agent",
                "Knowledge Agent",
                "Consultation Agent",
                "Safety Agent",
            ],
        ),
    ],
)
def test_graph_routing_trace_and_response(services, feature_dict, mode, expected):
    """Mỗi intent phải chạy đúng node và trả trace cùng schema hợp lệ."""
    workflow = Workflow(Settings(), *services)
    features = PatientFeatures(**feature_dict) if mode != "knowledge" else None
    question = "Kiến thức cơ bản?" if mode != "prediction" else ""
    result = workflow.run("test-request", question, features)
    assert result.intent == mode
    assert [entry.agent for entry in result.agent_trace] == expected
    assert all(entry.latency_ms >= 0 for entry in result.agent_trace)
    assert result.safety_status == "passed"
    if mode == "prediction":
        services[1].retrieve.assert_not_called()
        services[2].generate.assert_not_called()
    else:
        assert result.citations[0].citation_id == "S1"


def test_empty_evidence_does_not_call_llm(services):
    """Không có evidence phải fallback mà không gọi mô hình sinh trả lời."""
    services[1].retrieve.return_value = []
    result = Workflow(Settings(), *services).run("x", "Câu hỏi")
    assert result.safety_status == "fallback" and not result.citations
    services[2].generate.assert_not_called()


def test_timeout_fallback(services):
    """Lỗi dịch vụ phải xuất hiện trong trace và chuyển câu trả lời sang fallback."""
    services[2].generate.side_effect = ServiceError("Gemini đang tạm thời không khả dụng.")
    result = Workflow(Settings(), *services).run("x", "Câu hỏi")
    assert result.errors and result.agent_trace[-2].status == "error"
    assert result.safety_status == "fallback"


def test_invalid_citation_and_unsafe_output(services):
    """Citation sai hoặc nội dung chẩn đoán phải bị Safety loại bỏ."""
    services[2].generate.return_value.claims[0].citation_ids = ["S999"]
    result = Workflow(Settings(), *services).run("x", "Câu hỏi")
    assert result.safety_status == "fallback" and not result.citations
    services[2].generate.return_value.claims[0].citation_ids = ["S1"]
    services[2].generate.return_value.claims[0].text = "Bạn chắc chắn mắc tiểu đường."
    assert Workflow(Settings(), *services).run("x", "Câu hỏi").safety_status == "fallback"


@pytest.mark.parametrize(
    "query", ["Kê thuốc giúp tôi", "Liều dùng insulin bao nhiêu?", "Tôi có bị tiểu đường không?"]
)
def test_unsafe_request_early_fallback(services, query):
    """Yêu cầu ngoài phạm vi đi thẳng từ Coordinator tới Safety."""
    result = Workflow(Settings(), *services).run("x", query)
    assert [entry.agent for entry in result.agent_trace] == ["Coordinator", "Safety Agent"]
    assert result.safety_status == "fallback"
    services[2].generate.assert_not_called()


def test_api_routes_validation_and_errors(services, feature_dict):
    """Kiểm tra validation, response, request ID và mã HTTP khi model lỗi."""
    workflow = Workflow(Settings(), *services)
    app.dependency_overrides[get_workflow] = lambda: workflow
    try:
        client = TestClient(app)
        assert client.post("/api/v1/analyze", json={}).status_code == 422
        assert client.post("/api/v1/chat", json={"user_query": " "}).status_code == 422
        bad = client.post("/api/v1/predict", json={"patient_features": {"Age": 45}})
        assert bad.status_code == 422 and "input" not in bad.text
        prediction = client.post("/api/v1/predict", json={"patient_features": feature_dict})
        assert prediction.status_code == 200 and prediction.json()["model_score"] == 0.3
        response = client.post(
            "/api/v1/analyze",
            json={"patient_features": feature_dict, "user_query": "Kiến thức cơ bản?"},
        )
        assert response.status_code == 200
        assert response.json()["request_id"] == response.headers["X-Request-ID"]
        services[0].predict.side_effect = ServiceError("Chưa có model.", "model_missing")
        assert (
            client.post("/api/v1/predict", json={"patient_features": feature_dict}).status_code
            == 503
        )
    finally:
        app.dependency_overrides.clear()
