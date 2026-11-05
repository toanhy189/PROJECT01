"""Ghép các Agent thành đồ thị tuần tự và ghi trace từ node thực sự chạy."""

import logging
import time
from collections.abc import Callable
from functools import lru_cache

from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from backend.agents.nodes import Agents, coordinate
from backend.agents.safety import safety_node
from backend.core.config import Settings, get_settings
from backend.core.errors import ServiceError
from backend.graph.state import AgentState
from backend.llm.llm_provider import LLMProvider
from backend.ml.inference import Predictor
from backend.ml.tools import ModelTools, profile_hash
from backend.rag.retriever import Retriever
from backend.schemas.api import AnalysisResponse
from backend.schemas.features import PatientFeatures

logger = logging.getLogger("diabetes.graph")


def traced(name: str, action: Callable) -> Callable:
    """Bọc node để đo latency và chuyển lỗi dịch vụ thành dữ liệu fallback."""

    def invoke(state: AgentState) -> dict:
        """Chạy một node và nối trạng thái, thời gian thực vào trace hiện tại."""
        start = time.perf_counter()
        status = "ok"
        try:
            update = action(state)
            if update.get("safety_status") == "fallback":
                status = "fallback"
        except ServiceError as exc:
            # Giữ lỗi trong state để Safety tạo fallback; không làm mất trace các node trước.
            logger.warning(
                "request_id=%s agent=%s error_code=%s", state["request_id"], name, exc.code
            )
            update = {"errors": state.get("errors", []) + [str(exc)]}
            status = "error"
        elapsed = round((time.perf_counter() - start) * 1000, 3)
        # Đo tại lúc node chạy thay vì dựng sẵn danh sách agent hoặc thời gian minh họa.
        update["agent_trace"] = state.get("agent_trace", []) + [
            {"agent": name, "status": status, "latency_ms": elapsed}
        ]
        return update

    return invoke


def coordinator_route(state: AgentState) -> str:
    """Chặn yêu cầu ngoài phạm vi trước khi chọn nhánh dự đoán hoặc kiến thức."""
    if state.get("blocked_request"):
        return "safety"
    return "prediction" if state["intent"] in ("prediction", "combined") else "knowledge"


def prediction_route(state: AgentState) -> str:
    """Chỉ truy xuất thêm kiến thức khi yêu cầu có cả features và câu hỏi."""
    return "knowledge" if state["intent"] == "combined" else "safety"


def build_graph(agents: Agents) -> CompiledStateGraph:
    """Khai báo node và cạnh có điều kiện, rồi biên dịch workflow LangGraph."""
    graph = StateGraph(AgentState)
    graph.add_node("coordinator", traced("Coordinator", coordinate))
    graph.add_node("prediction", traced("Prediction Agent", agents.prediction))
    graph.add_node("knowledge", traced("Knowledge Agent", agents.knowledge))
    graph.add_node("consultation", traced("Consultation Agent", agents.consultation))
    graph.add_node("safety", traced("Safety Agent", safety_node))
    graph.add_edge(START, "coordinator")
    graph.add_conditional_edges(
        "coordinator",
        coordinator_route,
        {name: name for name in ("prediction", "knowledge", "safety")},
    )
    graph.add_conditional_edges(
        "prediction", prediction_route, {name: name for name in ("knowledge", "safety")}
    )
    graph.add_edge("knowledge", "consultation")
    graph.add_edge("consultation", "safety")
    graph.add_edge("safety", END)
    return graph.compile()


class Workflow:
    """Dùng chung các dịch vụ và đồ thị, khởi tạo state mới cho từng yêu cầu."""

    def __init__(
        self,
        settings: Settings,
        predictor: Predictor | None = None,
        retriever: Retriever | None = None,
        llm: LLMProvider | None = None,
    ) -> None:
        """Nhận dịch vụ được truyền vào hoặc tạo dịch vụ thật từ cấu hình."""
        self.predictor = predictor or Predictor(settings.artifact_dir)
        self.settings = settings
        self.tools = ModelTools(self.predictor, settings.artifact_dir)
        self.retriever = retriever or Retriever(settings)
        agents = Agents(settings, self.predictor, self.retriever, llm or LLMProvider(settings))
        self.graph = build_graph(agents)

    def run(
        self,
        request_id: str,
        question: str = "",
        features: PatientFeatures | None = None,
        focus: str | None = None,
    ) -> AnalysisResponse:
        """Chạy đồ thị với state mới và xác thực đầu ra bằng schema API."""
        state = self.graph.invoke(
            {
                "request_id": request_id,
                "user_query": question,
                "patient_features": features,
                "prediction_result": None,
                "retrieved_documents": [],
                "draft": None,
                "citations": [],
                "agent_trace": [],
                "errors": [],
                "focus": focus,
            }
        )
        response = AnalysisResponse.model_validate(
            {name: state[name] for name in AnalysisResponse.model_fields if name in state}
        )
        response.profile_hash = profile_hash(features) if features else None
        return response


@lru_cache(maxsize=1)
def get_workflow() -> Workflow:
    """Tái sử dụng workflow và bộ nạp model trong cùng process backend."""
    return Workflow(get_settings())
