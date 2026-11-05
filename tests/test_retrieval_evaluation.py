"""Kiểm tra gold/cache thật và phân biệt retrieval với đánh giá câu trả lời."""

import json

import pytest

from backend.core.config import ROOT, Settings
from backend.rag.corpus import fingerprint
from evaluation.evaluate_retrieval import CachedQueries, prepare_cases


def test_gold_matches_frozen_baseline_and_source_quotes():
    """Gold gán theo nguồn trước khi đo; mọi quote phải thuộc corpus đã khóa."""
    root = ROOT / "artifacts/baseline_niddk"
    if not (root / "corpus.json").exists():
        pytest.skip("Cần export baseline thật trước.")
    gold = json.loads((ROOT / "evaluation/retrieval_gold.json").read_text(encoding="utf-8"))
    frozen = json.loads((root / "retrieval_gold.json").read_text(encoding="utf-8"))
    assert fingerprint(gold) == fingerprint(frozen)
    rows = json.loads((root / "corpus.json").read_text(encoding="utf-8"))
    cases = prepare_cases(gold, rows)
    assert len(cases) == 50
    assert sum(not case["relevant_groups"] for case in cases) == 5
    assert {case["split"] for case in cases} == {"development", "heldout"}


def test_query_cache_never_fabricates_vectors(tmp_path):
    """Thiếu embedding thật phải báo lỗi; không tạo vector ngẫu nhiên để điền kết quả."""
    cache = CachedQueries(Settings(), tmp_path / "missing.json")
    with pytest.raises(KeyError):
        cache.embed(["Not cached"], query=True)


def test_gold_quote_missing_in_corpus_is_rejected():
    """Không cho bộ đo dùng quote bịa hoặc tài liệu không nằm trong corpus."""
    gold = {
        "cases": [{"case_id": "r01", "references": [{"document_id": "missing", "quote": "fake"}]}]
    }
    with pytest.raises(ValueError, match="Gold quote"):
        prepare_cases(gold, [])
