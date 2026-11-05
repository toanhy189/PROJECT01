"""Kiểm thử xuất bản corpus bằng embedding mock, không đụng chỉ mục thật."""

from unittest.mock import Mock

import pytest

from backend.core.errors import ServiceError
from backend.rag.corpus import collection_rows, fingerprint
from backend.rag.snapshot import load_active_snapshot
from ingestion.build_retrieval_indexes import build_snapshot
from ingestion.document_loader import Document
from ingestion.publish_corpus import publish_corpus


def wiki_document(revision: int = 42) -> Document:
    """Tạo bản wiki giả chỉ kiểm thử cơ chế version/vector reuse."""
    return Document(
        "wiki-test",
        "Test",
        f"https://en.wikipedia.org/w/index.php?oldid={revision}",
        "# Definition\n\nThis is a software-only definition for a sample entity.",
        "html",
        {
            "source_provider": "wikipedia",
            "revision_id": revision,
            "content_version": f"7:{revision}",
            "license": "Test license",
        },
    )


def test_publish_reuses_vectors_and_keeps_baseline_collection(graph_corpus):
    """Chỉ embed đoạn mới; chạy lặp hoặc đổi metadata revision không embed lại."""
    settings, _, ontology, annotations, store = graph_corpus
    build_snapshot(settings, store, ontology, annotations, activate=True)
    baseline = fingerprint(collection_rows(store.collection))
    service = Mock()
    service.embed.side_effect = lambda texts: [[0.0, 0.0, 1.0] + [0.0] * 765 for _ in texts]
    first = publish_corpus(
        settings, store, [wiki_document()], ontology, annotations, service, activate=True
    )
    assert first["new_embedding_texts"] == 1 and first["reused_vectors"] == 3
    assert fingerprint(collection_rows(store.collection)) == baseline
    assert load_active_snapshot(settings).store.collection.name != store.collection.name
    service.reset_mock()
    second = publish_corpus(
        settings, store, [wiki_document()], ontology, annotations, service, activate=True
    )
    assert second["new_embedding_texts"] == 0
    service.embed.assert_not_called()
    active_store = load_active_snapshot(settings).store
    publish_corpus(
        settings, active_store, [wiki_document(43)], ontology, annotations, service, activate=True
    )
    service.embed.assert_not_called()
    assert load_active_snapshot(settings).store.collection.count() == 4


def test_publish_embedding_failure_preserves_active_snapshot(graph_corpus):
    """API lỗi không được chuyển pointer hoặc sửa baseline collection."""
    settings, _, ontology, annotations, store = graph_corpus
    before = build_snapshot(settings, store, ontology, annotations, activate=True)
    service = Mock()
    service.embed.side_effect = ServiceError("Unavailable", "embedding_unavailable")
    with pytest.raises(ServiceError):
        publish_corpus(
            settings, store, [wiki_document()], ontology, annotations, service, activate=True
        )
    assert load_active_snapshot(settings).snapshot_id == before["snapshot_id"]
    assert store.collection.count() == 3
