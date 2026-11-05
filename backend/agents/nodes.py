"""Logic Coordinator và ba Agent xử lý dự đoán, bằng chứng, bản nháp trả lời."""

from backend.agents.safety import unsafe_request
from backend.core.config import Settings
from backend.core.text import plain_text
from backend.graph.state import AgentState
from backend.knowledge.clinical_rules import ClinicalRules, VerifiedAnswer
from backend.knowledge.measurements import bmi_input, scenario_change
from backend.ml.inference import Predictor
from backend.ml.tools import ModelTools
from backend.rag.context_builder import build_context
from backend.rag.retriever import Retriever


def coordinate(state: AgentState) -> dict:
    """Chọn intent theo input và đánh dấu yêu cầu cần chuyển thẳng Safety."""
    has_features = state.get("patient_features") is not None
    has_question = bool(state.get("user_query", "").strip())
    intent = (
        "combined"
        if has_features and has_question
        else "prediction"
        if has_features
        else "knowledge"
    )
    return {"intent": intent, "blocked_request": unsafe_request(state.get("user_query", ""))}


class Agents:
    """Gom các node chuyên trách với dịch vụ model, retriever và Gemini được truyền vào."""

    def __init__(self, settings: Settings, predictor, retriever, llm) -> None:
        """Giữ các dịch vụ dùng chung để node có thể chạy thật hoặc dùng mock khi test."""
        self.settings = settings
        self.predictor = predictor
        self.retriever = retriever
        self.llm = llm
        self.clinical = ClinicalRules()
        self.tools = (
            ModelTools(predictor, settings.artifact_dir)
            if isinstance(predictor, Predictor)
            else None
        )

    def prediction(self, state: AgentState) -> dict:
        """Gọi mô hình local và ghi kết quả phân loại vào state."""
        return {"prediction_result": self.predictor.predict(state["patient_features"])}

    def knowledge(self, state: AgentState) -> dict:
        """Truy xuất bằng chứng và dựng context có ID nguồn, chưa sinh câu trả lời."""
        question = state["user_query"]
        features = state.get("patient_features")
        delta, ambiguous = scenario_change(question, state.get("focus"))
        if delta is not None or ambiguous:
            if ambiguous or features is None or self.tools is None:
                answer = VerifiedAnswer(
                    "Bạn muốn thay đổi chỉ số nào? Để thử tăng/giảm BMI, "
                    "hãy nhập đủ 21 trường ở trang Phân loại, "
                    "rồi nêu rõ thay đổi BMI cần thử.",
                    needs_clarification=True,
                )
                scenario = None
            else:
                try:
                    scenario = self.tools.scenario(features, {"BMI": features.BMI + delta})
                    answer = VerifiedAnswer(
                        f"Giữ nguyên 20 thông tin còn lại, thử BMI từ {features.BMI:g} "
                        f"thành {features.BMI + delta:g}. "
                        f"Điểm mô hình trước: {scenario['before']['model_score']:.4f}; "
                        f"sau: {scenario['after']['model_score']:.4f}. "
                        f"Chênh lệch: {scenario['score_delta']:+.4f}. Hồ sơ gốc không thay đổi. "
                        "Đây là độ nhạy của mô hình, không biểu thị mức giảm nguy cơ bệnh "
                        "hoặc hiệu quả điều trị."
                    )
                except ValueError:
                    scenario = None
                    answer = VerifiedAnswer(
                        "BMI bản thử vượt miền đầu vào mô hình hoặc thay đổi chưa hợp lệ. "
                        "Hãy kiểm tra lại; hồ sơ gốc được giữ nguyên.",
                        needs_clarification=True,
                    )
            return {
                "tool_answer": answer,
                "scenario_result": scenario,
                "retrieval_trace": {"mode": "model_scenario", "warnings": []},
                "citations": [],
            }
        observation = bmi_input(question, features)
        if observation is not None:
            answer = self.clinical.assess_bmi(observation)
            return {
                "tool_answer": answer,
                "measurement_result": answer.details,
                "citations": list(answer.citations),
                "retrieval_trace": {
                    "mode": "sourced_rule",
                    "rule_id": (answer.details or {}).get("rule_id"),
                    "warnings": [],
                    "graph": {
                        "status": "not_queried_rule_answer",
                        "paths": [],
                        "linked_entities": [],
                    },
                },
            }
        if (
            features is not None
            and self.tools
            and "so sanh" in plain_text(question)
            and "mo hinh" in plain_text(question)
        ):
            comparison = self.tools.compare(features)
            lines = [
                f"{item['model_name']}: điểm {item['model_score']:.4f}, "
                f"ngưỡng {item['threshold']:.4f}, lớp {item['predicted_class']}."
                for item in comparison["models"]
            ]
            lines += [item["message"] for item in comparison["errors"]]
            return {
                "tool_answer": VerifiedAnswer(
                    "\n\n".join(lines)
                    + "\n\nMỗi mô hình dùng ngưỡng riêng; không cộng các điểm thành xác suất bệnh."
                ),
                "retrieval_trace": {"mode": "model_comparison", "warnings": []},
                "citations": [],
            }
        trace = {}
        if isinstance(self.retriever, Retriever):
            result = self.retriever.retrieve_with_trace(state["user_query"])
            documents, trace = result.documents, result.trace
        else:
            documents = self.retriever.retrieve(state["user_query"])
        context, citations = build_context(documents, self.settings.context_max_chars)
        used = {citation.chunk_id for citation in citations}
        trace["context_chunk_ids"] = sorted(used)
        for path in trace.get("graph", {}).get("paths", []):
            path["used_in_context"] = set(path["chunk_ids"]).issubset(used)
        return {
            "retrieved_documents": documents,
            "context": context,
            "citations": citations,
            "retrieval_trace": trace,
        }

    def consultation(self, state: AgentState) -> dict:
        """Chỉ gọi Gemini khi có context và không có lỗi dịch vụ trước đó."""
        if state.get("tool_answer") is not None or not state.get("context") or state.get("errors"):
            return {"draft": None}
        return {
            "draft": self.llm.generate(
                state["user_query"], state["context"], state.get("prediction_result")
            )
        }
