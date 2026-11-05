"""Kiểm thử đáp án tham chiếu, công thức retrieval và cách chấm groundedness."""

import json
from unittest.mock import Mock

import pytest

from backend.core.config import ROOT, Settings
from backend.core.errors import ServiceError
from backend.rag.retriever import Evidence
from evaluation.evaluate_rag import apply_human_ratings, evaluate, load_cases, ranking_metrics


def test_evaluation_waits_only_between_cases(monkeypatch):
    """Pacing không tạo lời gọi thừa; hai câu chỉ có một khoảng nghỉ ở giữa."""
    delays = []
    monkeypatch.setattr("evaluation.evaluate_rag.time.sleep", delays.append)
    retriever, llm = Mock(), Mock()
    retriever.retrieve.return_value = []
    cases = [
        {
            "case_id": str(i),
            "question": "Kiểm thử",
            "reference_answer": "Kiểm thử",
            "relevant_chunk_ids": ["known"],
        }
        for i in range(2)
    ]
    result = evaluate(Settings(), cases, retriever, llm, delay_seconds=7)
    assert delays == [7]
    assert result["request_delay_seconds"] == 7
    assert result["answer_cases_fallback"] == 2


def test_retrieval_metrics_survive_generation_failure():
    """LLM lỗi không được làm mất metrics và bằng chứng đã truy xuất thành công."""
    retriever, llm = Mock(), Mock()
    metadata = {
        "document_id": "test",
        "chunk_id": "chunk",
        "title": "Kiểm thử",
        "section": "Kiểm thử",
        "source_url": "https://www.niddk.nih.gov/health-information/diabetes",
    }
    retriever.retrieve.return_value = [
        Evidence("Evidence only for a software regression test.", metadata, 0.1)
    ]
    llm.generate.side_effect = ServiceError("Gemini quá thời gian chờ.", "llm_timeout")
    report = evaluate(
        Settings(),
        [
            {
                "case_id": "x",
                "question": "Kiểm thử",
                "reference_answer": "Kiểm thử",
                "relevant_chunk_ids": ["chunk"],
            }
        ],
        retriever,
        llm,
    )
    assert report["status"] == "incomplete" and report["cases_completed"] == 0
    assert report["retrieval_cases_completed"] == 1
    assert report["recall_at_k"] == 1.0 and report["mrr"] == 1.0
    assert report["results"][0]["error_codes"] == ["llm_timeout"]
    assert report["results"][0]["retrieved_sources"][0]["chunk_id"] == "chunk"


def test_reference_cases_are_present_in_real_corpus():
    """Bảo đảm quote tham chiếu xuất hiện trong chunk của tài liệu đã tải."""
    if not (ROOT / "data/knowledge/overview.md").is_file():
        pytest.skip("Cần tải tài liệu nguồn thật trước kiểm thử tham chiếu.")
    cases = load_cases(
        ROOT / "evaluation/rag_questions.json", ROOT / "data/knowledge/manifest.json"
    )
    assert len(cases) == 10
    assert all(case["relevant_chunk_ids"] for case in cases)


def test_rank_metrics_known_result():
    """Đối chiếu Recall và MRR với ví dụ có thứ hạng biết trước."""
    metrics = ranking_metrics(["a", "b", "c"], ["b", "d"])
    assert metrics["recall_at_k"] == 0.5
    assert metrics["reciprocal_rank"] == 0.5


def test_no_evidence_has_no_fabricated_generation():
    """Bảo đảm không gọi LLM hoặc bịa điểm groundedness khi không có evidence."""
    retriever, llm = Mock(), Mock()
    retriever.retrieve.return_value = []
    report = evaluate(
        Settings(),
        [
            {
                "case_id": "test",
                "question": "test",
                "reference_answer": "test",
                "relevant_chunk_ids": ["known"],
            }
        ],
        retriever,
        llm,
    )
    assert report["recall_at_k"] == 0
    assert report["citation_correctness_rule_check"] is None
    assert report["groundedness_human"] is None
    llm.generate.assert_not_called()


def test_human_ratings_must_match_claims(tmp_path):
    """Bản chấm phải khớp số claim trước khi được tính groundedness."""
    report = {"results": [{"case_id": "x", "errors": [], "claims": [{}, {}]}]}
    path = tmp_path / "ratings.json"
    path.write_text(
        json.dumps(
            [
                {
                    "case_id": "x",
                    "supported_claims": [True, False],
                    "reviewer": "Người kiểm thử",
                    "notes": "Đã đối chiếu nguồn.",
                }
            ]
        ),
        encoding="utf-8",
    )
    apply_human_ratings(report, path)
    assert report["groundedness_human"] == 0.5
    report["results"][0]["claims"] = []
    with pytest.raises(ValueError):
        apply_human_ratings(report, path)
