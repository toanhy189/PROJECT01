"""Đánh giá truy xuất RAG, kiểm tra trích dẫn và nhận bản chấm thủ công."""

import argparse
import json
import time
from pathlib import Path

import numpy as np

from backend.agents.safety import safety_node
from backend.core.config import ROOT, Settings, get_settings
from backend.core.errors import ServiceError
from backend.llm.llm_provider import GeneratedAnswer, LLMProvider
from backend.rag.citation_validator import normalize, validate_citations
from backend.rag.context_builder import build_context
from backend.rag.retriever import Retriever
from ingestion.chunker import chunk_document
from ingestion.document_loader import load_document


def load_cases(questions: Path, manifest: Path) -> list[dict]:
    """Đối chiếu quote tham chiếu với corpus và xác định các chunk cần truy xuất."""
    cases = json.loads(questions.read_text(encoding="utf-8"))
    entries = json.loads(manifest.read_text(encoding="utf-8"))
    corpus = {}
    for item in entries:
        document = load_document(
            manifest.parent / item["path"], item["document_id"], item["title"], item["source_url"]
        )
        corpus[item["document_id"]] = chunk_document(document)
    if len({case["case_id"] for case in cases}) != len(cases):
        raise ValueError("Case ID phải duy nhất.")
    for case in cases:
        # Gold chunk phải chứa quote tham chiếu, không chỉ có cùng tên tài liệu.
        relevant = [
            chunk.chunk_id
            for chunk in corpus.get(case["document_id"], [])
            if normalize(case["reference_quote"]) in normalize(chunk.text)
        ]
        if not relevant:
            raise ValueError(f"Đáp án tham chiếu không có trong corpus: {case['case_id']}")
        case["relevant_chunk_ids"] = relevant
    return cases


def ranking_metrics(retrieved_ids: list[str], relevant_ids: list[str]) -> dict:
    """Tính Recall@K và nghịch đảo thứ hạng của chunk liên quan đầu tiên."""
    relevant = set(relevant_ids)
    return {
        "recall_at_k": len(set(retrieved_ids) & relevant) / len(relevant),
        "reciprocal_rank": next(
            (1 / rank for rank, key in enumerate(retrieved_ids, 1) if key in relevant), 0.0
        ),
    }


def evaluate(
    settings: Settings, cases: list[dict], retriever=None, llm=None, *, delay_seconds: float = 0
) -> dict:
    """Chạy từng câu hỏi, đo thời gian và tổng hợp kết quả có phân biệt lỗi dịch vụ."""
    retriever = retriever or Retriever(settings)
    llm = llm or LLMProvider(settings)
    if not 0 <= delay_seconds <= 60:
        raise ValueError("Thời gian nghỉ giữa câu phải trong khoảng 0–60 giây.")
    rows = []
    for index, case in enumerate(cases):
        # Nghỉ ngoài khoảng đo latency để giảm lỗi RPM mà không làm sai thời gian xử lý.
        if index and delay_seconds:
            time.sleep(delay_seconds)
        started = time.perf_counter()
        row = {
            "case_id": case["case_id"],
            "question": case["question"],
            "reference_answer": case["reference_answer"],
            "errors": [],
            "error_codes": [],
        }
        try:
            evidence = retriever.retrieve(case["question"])
            row.update(
                ranking_metrics(
                    [item.metadata["chunk_id"] for item in evidence], case["relevant_chunk_ids"]
                )
            )
            context, citations = build_context(evidence, settings.context_max_chars)
            # Giữ bằng chứng truy xuất được kể cả khi bước sinh câu trả lời bị lỗi.
            row["retrieved_sources"] = [source.model_dump() for source in citations]
            draft = llm.generate(case["question"], context) if citations else None
            row["claims"] = [claim.model_dump() for claim in draft.claims] if draft else []
            row["citation_checks_passed"] = (
                sum(
                    validate_citations(
                        GeneratedAnswer(claims=[claim], insufficient_evidence=False), citations
                    )[0]
                    for claim in draft.claims
                )
                if draft
                else 0
            )
            safe = safety_node(
                {
                    "intent": "knowledge",
                    "draft": draft,
                    "citations": citations,
                    "errors": [],
                    "blocked_request": False,
                }
            )
            row["answer"] = safe["generated_answer"]
            row["safety_status"] = safe["safety_status"]
        except ServiceError as exc:
            row["errors"].append(str(exc))
            row["error_codes"].append(exc.code)
        row["latency_ms"] = (time.perf_counter() - started) * 1000
        rows.append(row)
    completed = [row for row in rows if not row["errors"]]
    # Chất lượng retrieval vẫn đo được khi LLM lỗi; không loại mất các kết quả này.
    retrieved = [row for row in rows if "recall_at_k" in row]
    # Tỷ lệ citation tính theo từng claim ở các case không lỗi, không gán 0 cho dữ liệu thiếu.
    total_claims = sum(len(row["claims"]) for row in completed)
    checked = sum(row["citation_checks_passed"] for row in completed)
    return {
        "status": "completed" if len(completed) == len(rows) else "incomplete",
        "cases_requested": len(cases),
        "cases_completed": len(completed),
        "retrieval_cases_completed": len(retrieved),
        "answer_cases_passed": sum(row.get("safety_status") == "passed" for row in completed),
        "answer_cases_fallback": sum(row.get("safety_status") == "fallback" for row in completed),
        "request_delay_seconds": delay_seconds,
        "k": settings.retrieval_k,
        "embedding_model": settings.gemini_embedding_model,
        "llm_model": settings.gemini_llm_model,
        "recall_at_k": float(np.mean([row["recall_at_k"] for row in retrieved]))
        if retrieved
        else None,
        "mrr": float(np.mean([row["reciprocal_rank"] for row in retrieved])) if retrieved else None,
        "citation_correctness_rule_check": checked / total_claims if total_claims else None,
        "groundedness_human": None,
        "groundedness_note": "Cần người đọc đối chiếu từng claim với retrieved_sources; kiểm tra quote không chứng minh suy diễn ngữ nghĩa.",
        "latency_mean_ms": float(np.mean([row["latency_ms"] for row in rows])) if rows else None,
        "latency_p95_ms": float(np.percentile([row["latency_ms"] for row in rows], 95))
        if rows
        else None,
        "results": rows,
    }


def apply_human_ratings(report: dict, ratings_path: Path) -> None:
    """Kiểm tra bản chấm từng claim rồi cập nhật groundedness trên phần đã chấm."""
    ratings = json.loads(ratings_path.read_text(encoding="utf-8"))
    rows = {row["case_id"]: row for row in report["results"] if not row["errors"]}
    seen, supported, total = set(), 0, 0
    for rating in ratings:
        key = rating["case_id"]
        if key in seen or key not in rows:
            raise ValueError("Bản chấm trùng ID hoặc không khớp kết quả chạy.")
        seen.add(key)
        # Chấm theo từng claim thay vì gộp cả câu trả lời.
        labels = rating["supported_claims"]
        if len(labels) != len(rows[key]["claims"]) or any(
            type(value) is not bool for value in labels
        ):
            raise ValueError("Số đánh giá không khớp claims hoặc nhãn không phải bool.")
        if not rating.get("reviewer") or not rating.get("notes"):
            raise ValueError("Cần người đánh giá và nhận xét đối chiếu.")
        supported += sum(labels)
        total += len(labels)
    report["groundedness_human"] = supported / total if total else None
    report["human_rated_cases"] = len(seen)
    report["human_rated_claims"] = total


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Đánh giá RAG với nguồn đã ingest")
    parser.add_argument("--questions", type=Path, default=ROOT / "evaluation/rag_questions.json")
    parser.add_argument("--output", type=Path, default=ROOT / "artifacts/rag_metrics.json")
    parser.add_argument("--ratings", type=Path)
    parser.add_argument(
        "--delay-seconds",
        type=float,
        default=7,
        help="Nghỉ giữa các câu để hạn chế rate limit, mặc định 7 giây",
    )
    parser.add_argument(
        "--rate-existing", type=Path, help="File kết quả cũ để chấm, không gọi Gemini lại"
    )
    args = parser.parse_args()
    if not 0 <= args.delay_seconds <= 60:
        parser.error("--delay-seconds phải nằm trong khoảng 0–60 giây.")
    if args.rate_existing:
        result = json.loads(args.rate_existing.read_text(encoding="utf-8"))
        if not args.ratings:
            parser.error("Cần --ratings khi chấm kết quả đã chạy.")
    else:
        settings = get_settings()
        if not settings.gemini_api_key:
            parser.exit(1, "Cần GEMINI_API_KEY và chỉ mục thật để đánh giá RAG.\n")
        result = evaluate(
            settings,
            load_cases(args.questions, ROOT / "data/knowledge/manifest.json"),
            delay_seconds=args.delay_seconds,
        )
    if args.ratings:
        apply_human_ratings(result, args.ratings)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(
        json.dumps(
            {key: value for key, value in result.items() if key != "results"}, ensure_ascii=True
        )
    )
    raise SystemExit(0 if result["status"] == "completed" else 1)
