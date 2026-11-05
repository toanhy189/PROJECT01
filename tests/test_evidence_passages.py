"""Kiểm tra lấy bằng chứng nguyên văn, không phụ thuộc Gemini hoặc mạng."""

import pytest

from backend.llm.evidence import build_passage_catalog, resolve_passages
from backend.llm.llm_provider import Claim, GeneratedAnswer
from backend.rag.citation_validator import validate_citations
from backend.rag.context_builder import build_context
from backend.rag.models import Evidence
from backend.schemas.api import Citation


def make_context(text: str) -> tuple[str, list[Citation]]:
    """Dùng chính context builder để giữ đúng hợp đồng giữa các bước."""
    return build_context(
        [
            Evidence(
                text,
                {
                    "chunk_id": "test-chunk",
                    "document_id": "test-doc",
                    "title": "Tài liệu kiểm thử",
                    "section": "Mục kiểm thử",
                    "source_url": "https://example.org/test",
                },
            )
        ]
    )


def test_selected_passages_preserve_order_and_intervening_negation():
    """Chọn hai đầu vẫn giữ đoạn giữa, không ghép câu hoặc bỏ phủ định."""
    text = (
        "First paragraph for a software test.\n\n"
        "This does NOT establish a diagnosis.\n\n"
        "Last paragraph for a software test."
    )
    context, sources = make_context(text)
    catalog = build_passage_catalog(context)
    quotes = resolve_passages(["S1.P3", "S1.P1"], catalog)
    assert quotes == {"S1": text}
    draft = GeneratedAnswer(
        claims=[
            Claim(
                text="Nhận định kiểm thử.",
                citation_ids=["S1"],
                supporting_quotes=quotes,
            )
        ],
        insufficient_evidence=False,
    )
    assert validate_citations(draft, sources)[0]


def test_lists_tables_and_footnotes_remain_verbatim():
    """Không bỏ mục danh sách, ký hiệu Markdown, bảng hoặc chú thích HTML."""
    text = (
        "Test list<sup>1</sup>\n\n- first item\n- omitted item\n- last item\n\n"
        "| Test | Value |\n| --- | --- |\n| Sample | 35 |"
    )
    context, _ = make_context(text)
    catalog = build_passage_catalog(context)
    assert catalog["S1.P2"].text == "- first item\n- omitted item\n- last item"
    assert catalog["S1.P3"].text == text.split("\n\n")[2]
    assert resolve_passages(["S1.P1"], catalog)["S1"] == "Test list<sup>1</sup>"


def test_numeric_guard_still_rejects_converted_or_invented_numbers():
    """Chọn mã hợp lệ vẫn phải qua bộ kiểm tra số liệu của nhận định."""
    context, sources = make_context("The software test records a value of 9 pounds.")
    quotes = resolve_passages(["S1.P1"], build_passage_catalog(context))
    draft = GeneratedAnswer(
        claims=[
            Claim(
                text="Giá trị kiểm thử là 4 kg.",
                citation_ids=["S1"],
                supporting_quotes=quotes,
            )
        ],
        insufficient_evidence=False,
    )
    assert not validate_citations(draft, sources)[0]


def test_old_reordered_or_shortened_quotes_still_rejected():
    """Giữ nguyên hàng rào chặn quote đảo câu hoặc bỏ mục như lỗi thực tế."""
    _context, sources = make_context(
        "First sentence for testing. Second sentence for testing.\n\n"
        "- first item\n- important middle item\n- last item"
    )
    for quote in (
        "Second sentence for testing. First sentence for testing.",
        "- first item\n- last item",
    ):
        draft = GeneratedAnswer(
            claims=[
                Claim(
                    text="Nhận định kiểm thử.",
                    citation_ids=["S1"],
                    supporting_quotes={"S1": quote},
                )
            ],
            insufficient_evidence=False,
        )
        assert not validate_citations(draft, sources)[0]


def test_multiple_sources_keep_independent_text():
    """Mã đoạn không được lấy văn bản từ nhầm nguồn hoặc từ tiêu đề nguồn."""
    context = (
        "[S1] First — Heading\nFirst source text.\n\n[S2] Second — Heading\nSecond source text."
    )
    catalog = build_passage_catalog(context)
    assert resolve_passages(["S2.P1", "S1.P1"], catalog) == {
        "S2": "Second source text.",
        "S1": "First source text.",
    }
    with pytest.raises(ValueError):
        resolve_passages(["S1.P2"], catalog)


def test_wiki_policy_is_not_a_source_quote():
    """Ghi chú chính sách là chỉ dẫn của hệ thống, không phải nội dung tài liệu."""
    context = (
        "[S1] Wiki — Heading\n"
        "Nguồn bách khoa bổ sung; chỉ dùng cho định nghĩa/kiến thức nền.\n"
        "An encyclopedic paragraph for a software test."
    )
    catalog = build_passage_catalog(context)
    assert catalog["S1.P1"].text == "An encyclopedic paragraph for a software test."
    assert catalog["S1.P1"].background_only
