"""Kiểm thử pipeline RAG với Gemini mock và ChromaDB tạm thời thật."""

from types import SimpleNamespace
from unittest.mock import Mock

import httpx
import numpy as np
import pytest

from backend.core.config import Settings
from backend.core.errors import ServiceError
from backend.llm.llm_provider import Claim, GeneratedAnswer, LLMProvider
from backend.rag.citation_validator import clinical_numbers, normalize, validate_citations
from backend.rag.context_builder import build_context
from backend.rag.embedding_service import EmbeddingService
from backend.rag.retriever import Evidence, Retriever
from backend.rag.vector_store import VectorStore
from ingestion.chunker import chunk_document
from ingestion.document_loader import Document, load_document
from ingestion.text_cleaner import clean_text


def test_citation_whitespace_before_punctuation_is_equivalent():
    """Khoảng trắng từ HTML trước dấu câu không làm một quote thật thành quote giả."""
    assert normalize("a blood glucose meter , cannot diagnose diabetes.") == normalize(
        "a blood glucose meter, cannot diagnose diabetes."
    )
    assert normalize("cannot diagnose diabetes") != normalize("can diagnose diabetes")


def test_type_labels_are_not_clinical_measurements():
    """Bỏ số trong tên típ bệnh nhưng vẫn phải đối chiếu số liệu và phần trăm thật."""
    assert clinical_numbers("Tiểu đường típ 2 có 25% trong ví dụ [S1].") == {"25"}
    assert clinical_numbers("Type 1 diabetes, A1C 6.5% and glucose 126 mg/dL.") == {"6.5", "126"}


@pytest.fixture
def document():
    """Tạo văn bản dành riêng cho kiểm thử chunking, không giả làm nguồn y khoa."""
    return Document(
        "test-doc",
        "Tài liệu kiểm thử",
        "https://www.niddk.nih.gov/health-information/diabetes",
        "# Kiến thức\n\n" + "This is evidence about diabetes for a software test. " * 80,
    )


def test_cleaner_preserves_medical_units():
    """Làm sạch khoảng trắng phải giữ nguyên số liệu và ký hiệu đơn vị."""
    assert clean_text("  HbA1c  6.5%\n\n  126 mg/dL \x00") == "HbA1c 6.5%\n\n126 mg/dL"


def test_chunk_boundaries_and_metadata(document):
    """Chunk có ranh giới câu, ID lặp lại ổn định và metadata heading đúng."""
    chunks = chunk_document(document)
    assert len(chunks) > 1
    assert all(chunk.text.endswith(".") for chunk in chunks)
    assert all(len(chunk.text) <= 2000 for chunk in chunks)
    assert chunks[0].metadata["section"] == "Kiến thức"
    assert chunks == chunk_document(document)


def test_loader_markdown_and_pdf(tmp_path):
    """Đọc được Markdown UTF-8 và PDF văn bản tạo trong bài kiểm thử."""
    import pymupdf

    md = tmp_path / "test.md"
    md.write_text("# Nội dung\n\nVăn bản thật trong file kiểm thử.", encoding="utf-8")
    url = "https://www.niddk.nih.gov/health-information/diabetes"
    assert "Nội dung" in load_document(md, "x", "t", url).text
    pdf_path = tmp_path / "test.pdf"
    with pymupdf.open() as pdf:
        page = pdf.new_page()
        page.insert_text((72, 72), "PDF loader verification.")
        pdf.save(pdf_path)
    assert "PDF loader" in load_document(pdf_path, "x", "t", url).text


def test_embedding_task_types_and_normalization():
    """Query và document dùng đúng task type, vector đầu ra có chuẩn L2 bằng một."""
    client = Mock()
    client.models.embed_content.return_value = SimpleNamespace(
        embeddings=[SimpleNamespace(values=[1.0] * 768)]
    )
    service = EmbeddingService(Settings(), client)
    vectors = service.embed(["test"], query=True)
    assert np.linalg.norm(vectors[0]) == pytest.approx(1)
    assert client.models.embed_content.call_args.kwargs["config"].task_type == "RETRIEVAL_QUERY"
    service.embed(["document"])
    assert client.models.embed_content.call_args.kwargs["config"].task_type == "RETRIEVAL_DOCUMENT"


def test_embedding_and_llm_timeout():
    """Timeout từ Gemini phải thành ServiceError với thông báo sạch."""
    client = Mock()
    client.models.embed_content.side_effect = httpx.ReadTimeout("test")
    with pytest.raises(ServiceError, match="embedding"):
        EmbeddingService(Settings(), client).embed(["test"])
    client.models.generate_content.side_effect = httpx.ReadTimeout("test")
    with pytest.raises(ServiceError, match="Gemini"):
        LLMProvider(Settings(), client).generate("test", "[S1] Test — Test\nEvidence for test.")


def test_chroma_idempotence_retrieval_and_model_mismatch(tmp_path, document):
    """Kiểm tra upsert lặp, tìm kiếm Chroma và từ chối embedding khác cấu hình."""
    settings = Settings(chroma_dir=tmp_path / "chroma")
    store = VectorStore(settings)
    chunks = chunk_document(document)
    vector = [1.0] + [0.0] * 767
    store.replace_document(document.document_id, chunks, [vector] * len(chunks))
    store.replace_document(document.document_id, chunks, [vector] * len(chunks))
    assert store.collection.count() == len(chunks)
    embeddings = Mock()
    embeddings.embed.return_value = [vector]
    found = Retriever(settings, embeddings, store).retrieve("test")
    assert found and found[0].metadata["document_id"] == "test-doc"
    store.replace_document(document.document_id, chunks[:1], [vector])
    assert store.collection.count() == 1
    with pytest.raises(ServiceError, match="re-index"):
        VectorStore(Settings(chroma_dir=settings.chroma_dir, embedding_dimension=1024))


def test_context_dedup_budget_and_citations(document):
    """Context khử trùng, tuân ngân sách và loại citation ID ngoài evidence."""
    chunk = chunk_document(document)[0]
    evidence = Evidence(chunk.text, chunk.metadata, 0.1)
    context, sources = build_context([evidence, evidence])
    assert len(sources) == 1
    assert context.startswith("[S1]")
    assert build_context([evidence], max_chars=10) == ("", [])
    answer = GeneratedAnswer(
        insufficient_evidence=False,
        claims=[
            Claim(
                text="Đây là nhận định kiểm thử.",
                citation_ids=["S1"],
                supporting_quotes={"S1": "This is evidence about diabetes for a software test."},
            )
        ],
    )
    assert validate_citations(answer, sources)[0]
    answer.claims[0].citation_ids = ["S99"]
    assert not validate_citations(answer, sources)[0]


def test_reject_fabricated_quote_and_numeric_claim(document):
    """Từ chối quote bịa hoặc số liệu không được đoạn trích hỗ trợ."""
    chunk = chunk_document(document)[0]
    _, sources = build_context([Evidence(chunk.text, chunk.metadata, 0.1)])
    claim = Claim(
        text="Nhận định 99%.",
        citation_ids=["S1"],
        supporting_quotes={"S1": "This is evidence about diabetes for a software test."},
    )
    assert not validate_citations(
        GeneratedAnswer(claims=[claim], insufficient_evidence=False), sources
    )[0]
    claim.text = "Nhận định kiểm thử."
    claim.supporting_quotes["S1"] = "An invented quote that does not occur in evidence."
    assert not validate_citations(
        GeneratedAnswer(claims=[claim], insufficient_evidence=False), sources
    )[0]
