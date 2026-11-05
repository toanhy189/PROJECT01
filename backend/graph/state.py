"""Định nghĩa dữ liệu các node chia sẻ trong một lần chạy LangGraph."""

from typing import Literal, TypedDict

from backend.knowledge.clinical_rules import VerifiedAnswer
from backend.llm.llm_provider import GeneratedAnswer
from backend.rag.retriever import Evidence
from backend.schemas.api import Citation, PredictionResult
from backend.schemas.features import PatientFeatures


class AgentState(TypedDict, total=False):
    """Giữ input, kết quả trung gian, lỗi và trace; không lưu qua các yêu cầu."""

    request_id: str
    user_query: str
    patient_features: PatientFeatures | None
    intent: Literal["prediction", "knowledge", "combined"]
    prediction_result: PredictionResult | None
    retrieved_documents: list[Evidence]
    draft: GeneratedAnswer | None
    generated_answer: str
    citations: list[Citation]
    safety_status: str
    agent_trace: list[dict]
    errors: list[str]
    context: str
    blocked_request: bool
    retrieval_trace: dict
    tool_answer: VerifiedAnswer | None
    measurement_result: dict | None
    scenario_result: dict | None
    focus: str | None
