"""Kiểm tra phạm vi và nội dung trả lời bằng quy tắc cho MVP."""

import re

from backend.core.text import plain_text
from backend.graph.state import AgentState
from backend.rag.citation_validator import validate_citations
from backend.rag.semantic_validator import validate_clinical_meaning
from backend.rag.source_policy import wiki_claim_allowed
from backend.schemas.api import LIMITATIONS


def unsafe_request(query: str) -> bool:
    """Nhận diện một số yêu cầu chẩn đoán, kê thuốc hoặc hướng dẫn liều."""
    query = plain_text(query)
    return bool(
        re.search(
            r"ke (?:don|thuoc)|lieu (?:dung|thuoc)|tang lieu|giam lieu|ngung thuoc|"
            r"uong .{0,30}(?:mg|bao nhieu|may vien)|"
            r"prescrib|dosage|how much .{0,25}(?:insulin|metformin)|"
            r"(?:tiem|dung) .{0,35}(?:bao nhieu|may vien|lieu)|"
            r"(?:toi|minh|em) co (?:bi|mac) .{0,20}(?:tieu duong|benh)|"
            r"do i have diabetes|chan doan (?:cho|giup)",
            query,
        )
    )


def unsafe_answer(answer: str) -> bool:
    """Lọc một số khẳng định chẩn đoán và hướng dẫn dùng thuốc trong bản nháp."""
    text = plain_text(answer)
    # Loại trừ đơn vị nồng độ mg/dL để tránh nhầm dữ liệu xét nghiệm với liều thuốc.
    return bool(
        re.search(
            r"\b\d+(?:[.,]\d+)?\s*(?:mg|mcg|ml|iu|vien|units?|don vi)\b(?!\s*/\s*(?:dl|l)\b)|"
            r"ban (?:chac chan |da )?(?:bi|mac) (?:benh )?tieu duong|"
            r"you (?:definitely )?have diabetes|"
            r"(?:tang|giam|ngung|doi) (?:lieu|thuoc)|"
            r"(?:hay|nen|can) (?:uong|dung|tiem) .{0,30}(?:thuoc|insulin|metformin)|"
            r"(?:xac suat|nguy co) .{0,40}\d+(?:[.,]\d+)?\s*%",
            text,
        )
    )


def prediction_summary(state: AgentState) -> str:
    """Diễn giải điểm và lớp theo nhãn khảo sát, không chuyển thành chẩn đoán."""
    prediction = state.get("prediction_result")
    if not prediction:
        return ""
    label = (
        "nhóm tiền tiểu đường hoặc tiểu đường"
        if prediction.predicted_class == 1
        else "nhóm không tiểu đường"
    )
    return (
        f"Điểm mô hình: {prediction.model_score:.4f}; ngưỡng: {prediction.threshold:.4f}. "
        f"Phân loại lớp {prediction.predicted_class}: {label} theo nhãn khảo sát. "
    )


def safety_node(state: AgentState) -> dict:
    """Kiểm tra draft, chọn nguồn đã dùng hoặc trả fallback kèm giới hạn hệ thống."""
    summary = prediction_summary(state)
    if state.get("blocked_request"):
        return {
            "generated_answer": summary + "Hệ thống không chẩn đoán, kê thuốc hoặc hướng dẫn liều. "
            "Vui lòng trao đổi với bác sĩ về tình trạng và điều trị của bạn.\n\n" + LIMITATIONS,
            "citations": [],
            "safety_status": "fallback",
        }
    if state.get("errors"):
        return {
            "generated_answer": summary
            + "Chức năng chưa hoàn tất: "
            + " ".join(state["errors"])
            + "\n\n"
            + LIMITATIONS,
            "citations": [],
            "safety_status": "fallback",
        }
    if state["intent"] == "prediction":
        return {
            "generated_answer": summary + "\n\n" + LIMITATIONS,
            "citations": [],
            "safety_status": "passed",
        }
    tool_answer = state.get("tool_answer")
    if tool_answer is not None:
        unchanged = tool_answer.source_unchanged()
        text = (
            tool_answer.answer
            if unchanged
            else "Nguồn đã đổi trong lúc xử lý. Hãy kiểm tra lại quy tắc trước khi đối chiếu."
        )
        return {
            "generated_answer": summary + text + "\n\n" + LIMITATIONS,
            "citations": list(tool_answer.citations) if unchanged else [],
            "safety_status": "fallback"
            if tool_answer.needs_clarification or not unchanged
            else "passed",
        }
    draft = state.get("draft")
    valid, reason = (
        validate_citations(draft, state.get("citations", []))
        if draft
        else (False, "Chưa có bằng chứng phù hợp trong kho tài liệu để trả lời câu hỏi này.")
    )
    if valid:
        valid, reason = validate_clinical_meaning(draft)
    if valid:
        for claim in draft.claims:
            sources = [
                source
                for source in state.get("citations", [])
                if source.citation_id in claim.citation_ids
            ]
            if not wiki_claim_allowed(claim.text, sources):
                valid, reason = (
                    False,
                    "Nguồn wiki chỉ bổ sung kiến thức nền; chưa đủ nguồn y khoa phù hợp cho nhận định này.",
                )
                break
    if valid:
        paragraphs = [
            claim.text + " " + " ".join(f"[{key}]" for key in claim.citation_ids)
            for claim in draft.claims
        ]
        answer = "\n\n".join(paragraphs)
        if unsafe_answer(answer):
            valid, reason = False, "Nội dung chưa vượt qua kiểm tra an toàn. Vui lòng hỏi bác sĩ."
    if not valid:
        return {
            "generated_answer": summary + reason + "\n\n" + LIMITATIONS,
            "citations": [],
            "safety_status": "fallback",
        }
    # Chỉ trả những nguồn thực sự được các claim sử dụng, tránh gắn nguồn không liên quan.
    used = {key for claim in draft.claims for key in claim.citation_ids}
    return {
        "generated_answer": summary + answer + "\n\n" + LIMITATIONS,
        "citations": [source for source in state["citations"] if source.citation_id in used],
        "safety_status": "passed",
    }
