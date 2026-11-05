"""Kiểm thử trace/API và chính sách nguồn, không gọi Gemini thật."""

from unittest.mock import Mock

from fastapi.testclient import TestClient

from backend.agents.safety import unsafe_request
from backend.graph.workflow import Workflow, get_workflow
from backend.main import app
from backend.rag.retriever import Retriever
from backend.rag.source_policy import wiki_claim_allowed
from backend.schemas.api import Citation
from ingestion.build_retrieval_indexes import build_snapshot


def test_retrieve_endpoint_returns_graph_path_without_llm(graph_corpus):
    """API demo trả graph/evidence thật từ corpus kiểm thử và không gọi mô hình sinh."""
    settings, _, ontology, annotations, store = graph_corpus
    build_snapshot(settings, store, ontology, annotations, activate=True)
    embeddings = Mock()
    embeddings.embed.return_value = [[1.0] + [0.0] * 767]
    llm = Mock()
    workflow = Workflow(settings, Mock(), Retriever(settings, embeddings, store), llm)
    app.dependency_overrides[get_workflow] = lambda: workflow
    try:
        client = TestClient(app)
        info = client.get("/api/v1/retrieval-info")
        assert info.status_code == 200 and info.json()["relations"] == 2
        result = client.post("/api/v1/retrieve", json={"user_query": "Alpha Gamma"})
        assert result.status_code == 200
        assert result.json()["trace"]["graph"]["paths"]
        assert result.json()["documents"]
        llm.generate.assert_not_called()
    finally:
        app.dependency_overrides.clear()


def test_wiki_only_claim_cannot_introduce_measurements():
    """Quote tồn tại vẫn chưa cho phép wiki đơn độc chứng minh ngưỡng y khoa."""
    source = Citation(
        citation_id="S1",
        document_id="wiki-test",
        chunk_id="a",
        title="Wiki",
        section="Definition",
        source_url="https://en.wikipedia.org/w/index.php?oldid=42",
        quote="Software definition.",
        source_provider="wikipedia",
    )
    assert wiki_claim_allowed("Đây là tên một thuật ngữ.", [source])
    assert not wiki_claim_allowed("Ngưỡng xét nghiệm là 6.5%.", [source])
    assert not wiki_claim_allowed("Nên dùng thuốc điều trị.", [source])


def test_vietnamese_injection_dosage_request_is_blocked():
    """Yêu cầu liều tiêm tiếng Việt phải được chặn trước các nhánh truy xuất."""
    assert unsafe_request("Tôi nên tiêm insulin bao nhiêu đơn vị tối nay?")
