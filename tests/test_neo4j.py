"""Kiểm thử schema, driver và fallback; không báo mock là kết nối Neo4j thật."""

from unittest.mock import Mock, patch

import pytest
from neo4j.exceptions import AuthError, ServiceUnavailable

from backend.core.config import Settings
from backend.core.errors import ServiceError
from backend.rag.corpus import fingerprint
from backend.rag.fusion import guard_vector_candidates
from backend.rag.knowledge_graph import ValidatedGraph, build_graph_data
from backend.rag.models import Evidence
from backend.rag.neo4j_connection import Neo4jConnection, close_connections, get_connection
from backend.rag.neo4j_schema import expected_links, graph_payload
from backend.rag.retriever import Retriever
from ingestion.build_retrieval_indexes import build_snapshot


def test_versioned_schema_retains_logical_ids_and_evidence(graph_corpus):
    """Hai phiên bản có ID vật lý khác nhau nhưng không đổi chunk ID của Chroma."""
    _, rows, ontology, annotations, _ = graph_corpus
    data = build_graph_data(rows, ontology, annotations)
    first = graph_payload("a" * 64, data, rows)
    second = graph_payload("b" * 64, data, rows)
    assert {item["chunk_id"] for item in first["Chunk"]} == {"a", "b", "c"}
    assert {item["uid"] for items in first.values() for item in items}.isdisjoint(
        {item["uid"] for items in second.values() for item in items}
    )
    assert len(first["RelationFact"]) == 2 and len(first["Evidence"]) == 3
    assert len(expected_links(first)) == 13
    assert first["Evidence"][0]["quote"] in " ".join(row["text"] for row in rows)


def test_duplicate_evidence_is_rejected(graph_corpus):
    """Không âm thầm đếm hoặc import evidence lặp."""
    _, rows, ontology, annotations, _ = graph_corpus
    data = build_graph_data(rows, ontology, annotations)
    data["evidence"].append(data["evidence"][0].copy())
    with pytest.raises(ValueError, match="Evidence"):
        ValidatedGraph(data, rows)


def test_driver_requires_password_and_hides_it():
    """Không thử đăng nhập bằng mật khẩu rỗng và không lộ mật khẩu trong repr."""
    settings = Settings(neo4j_password="")
    with pytest.raises(ServiceError, match="mật khẩu"):
        Neo4jConnection(settings)
    assert "private-password-value" not in repr(Settings(neo4j_password="private-password-value"))


@pytest.mark.parametrize(
    "error,code",
    [
        (AuthError("wrong credentials"), "neo4j_auth_failed"),
        (ServiceUnavailable("server down"), "neo4j_unavailable"),
    ],
)
def test_connection_errors_are_sanitized(error, code):
    """Sai xác thực và database dừng đều có mã lỗi an toàn cho fallback."""
    with patch("backend.rag.neo4j_connection.GraphDatabase.driver") as factory:
        connection = Neo4jConnection(Settings(neo4j_password="unit-test-only"))
        factory.return_value.session.return_value.__enter__.return_value.execute_read.side_effect = error
        with pytest.raises(ServiceError) as captured:
            connection.read("RETURN 1")
        assert captured.value.code == code
        assert "unit-test-only" not in str(captured.value)


def test_connection_pool_is_reused_and_closed():
    """Mỗi cấu hình dùng một driver; shutdown đóng pool và cho phép khởi tạo lại."""
    settings = Settings(neo4j_password="pool-unit-test-only")
    with patch("backend.rag.neo4j_connection.GraphDatabase.driver") as factory:
        first = get_connection(settings)
        assert get_connection(settings) is first
        close_connections()
        factory.return_value.close.assert_called_once()


def test_neo4j_failure_keeps_bm25_and_vector(graph_corpus):
    """Lỗi graph không làm hỏng hai nhánh truy xuất còn lại."""
    settings, _, ontology, annotations, store = graph_corpus
    build_snapshot(settings, store, ontology, annotations, activate=True)
    cfg = settings.model_copy(update={"graph_backend": "neo4j"})
    embeddings = Mock()
    embeddings.embed.return_value = [[1.0] + [0.0] * 767]
    with patch(
        "backend.rag.neo4j_graph.get_connection",
        side_effect=ServiceError("down", "neo4j_unavailable"),
    ):
        result = Retriever(cfg, embeddings, store).retrieve_with_trace("Alpha Gamma", 3)
    assert result.documents and result.trace["channel_counts"]["bm25"]
    assert result.trace["graph"]["status"] == "fallback"
    assert result.trace["graph"]["backend"] == "neo4j"
    assert "neo4j_unavailable_using_vector_bm25" in result.trace["warnings"]


def test_guarded_fusion_preserves_vector_set_and_adds_when_sparse():
    """Đồ thị chỉ đổi thứ tự top-k vector; khi thiếu mới bổ sung chunk bên ngoài."""
    vector = [Evidence(str(i), {"chunk_id": str(i)}) for i in range(5)]
    graph = Evidence("extra", {"chunk_id": "extra"})
    fused = [graph, *reversed(vector)]
    guarded = guard_vector_candidates(fused, vector, 5)
    assert {item.metadata["chunk_id"] for item in guarded[:5]} == {str(i) for i in range(5)}
    sparse = guard_vector_candidates(fused, vector[:1], 3)
    assert sparse[0].metadata["chunk_id"] == "0" and sparse[1] is graph


def test_failed_neo4j_migration_does_not_activate_snapshot(graph_corpus):
    """Database lỗi khi công bố bản mới không được đổi con trỏ active."""
    settings, _, ontology, annotations, store = graph_corpus
    build_snapshot(settings, store, ontology, annotations, activate=True)
    pointer = settings.retrieval_index_dir / "active.json"
    before = pointer.read_bytes()
    cfg = settings.model_copy(update={"graph_backend": "neo4j"})
    changed = [*annotations, {**annotations[0], "polarity": "negative"}]
    with (
        patch("ingestion.migrate_neo4j.get_connection", side_effect=ServiceError("down")),
        pytest.raises(ServiceError),
    ):
        build_snapshot(cfg, store, ontology, changed, activate=True)
    assert pointer.read_bytes() == before


@pytest.mark.parametrize("corruption", ["quote", "document_version"])
def test_record_validation_rejects_fabricated_quote(graph_corpus, corruption):
    """Quote hoặc phiên bản nguồn sai không được dùng trong câu trả lời."""
    from backend.rag.neo4j_graph import Neo4jGraph

    settings, rows, ontology, annotations, _ = graph_corpus
    data = build_graph_data(rows, ontology, annotations)
    graph = Neo4jGraph(data, rows, settings, "a" * 64, fingerprint(data))
    relation = data["relations"][0]
    ev = next(item for item in data["evidence"] if item["relation_id"] == relation["relation_id"])
    row = next(item for item in rows if item["chunk_id"] == ev["chunk_id"])
    record = {
        "fact": relation,
        "evidence": ev.copy(),
        "chunk": {
            "chunk_id": ev["chunk_id"],
            "document_id": ev["document_id"],
            "content_hash": fingerprint(row["text"]),
        },
        "document": {
            "document_id": ev["document_id"],
            "source_url": ev["source_url"],
            "content_version": ev["content_version"],
            "source_provider": ev["source_provider"],
        },
        "subject_id": relation["subject"],
        "object_id": relation["object"],
    }
    if corruption == "quote":
        record["evidence"]["quote"] = "fabricated"
    else:
        record["document"]["content_version"] = "wrong-version"
    with pytest.raises(ServiceError, match="Evidence"):
        graph._validate_records([record])


def test_empty_local_fallback_does_not_hide_embedding_error(graph_corpus):
    """Không có nguồn local thì giữ lỗi Gemini thay vì báo nhầm kho thiếu kiến thức."""
    settings, _, ontology, annotations, store = graph_corpus
    build_snapshot(settings, store, ontology, annotations, activate=True)
    cfg = settings.model_copy(update={"enable_hybrid_search": False})
    embeddings = Mock()
    embeddings.embed.side_effect = ServiceError("Missing GEMINI_API_KEY", "gemini_key_missing")
    with pytest.raises(ServiceError) as captured:
        Retriever(cfg, embeddings, store).retrieve_with_trace("Unrelated unknown terms")
    assert captured.value.code == "gemini_key_missing"
