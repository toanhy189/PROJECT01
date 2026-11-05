"""Kiểm thử GraphRAG, provenance, RRF và phiên bản bằng corpus phần mềm nhỏ."""

import json
from unittest.mock import Mock

import pytest

from backend.rag.corpus import collection_rows, fingerprint
from backend.rag.fusion import reciprocal_rank_fusion
from backend.rag.knowledge_graph import KnowledgeGraph, build_graph_data
from backend.rag.lexical import LexicalIndex, expand_query, link_entities
from backend.rag.models import Evidence
from backend.rag.retriever import Retriever
from backend.rag.snapshot import load_active_snapshot
from backend.rag.source_policy import source_allowed
from ingestion.build_retrieval_indexes import build_snapshot


def test_relation_has_multiple_independent_evidence(graph_corpus):
    """Một cạnh logic giữ nhiều nguồn; xóa một nguồn không xóa bằng chứng còn lại."""
    _, rows, ontology, annotations, _ = graph_corpus
    data = build_graph_data(rows, ontology, annotations)
    assert len(data["relations"]) == 2 and len(data["evidence"]) == 3
    reduced = build_graph_data(rows[1:], ontology, annotations)
    assert len(reduced["relations"]) == 2 and len(reduced["evidence"]) == 2
    assert all(item["document_id"] != "a" for item in reduced["evidence"])


def test_draft_relation_is_not_served_and_invalid_quote_is_rejected(graph_corpus):
    """Nháp chưa duyệt không được kích hoạt; quote thay đổi phải chặn xây graph."""
    _, rows, ontology, annotations, _ = graph_corpus
    draft = [{**item, "status": "draft"} for item in annotations]
    assert build_graph_data(rows, ontology, draft)["relations"] == []
    with pytest.raises(ValueError, match="Quote"):
        build_graph_data(rows, ontology, [{**annotations[0], "quote": "fabricated source"}])


def test_two_hop_path_keeps_original_direction_and_every_evidence(graph_corpus):
    """Đi ngược cạnh chỉ để tìm nguồn, không đổi RISK_FACTOR_FOR thành nguyên nhân."""
    _, rows, ontology, annotations, _ = graph_corpus
    graph = KnowledgeGraph(build_graph_data(rows, ontology, annotations), rows)
    found, trace = graph.search("Alpha Gamma", limit=5, max_hops=2)
    path = next(path for path in trace["paths"] if path["hops"] == 2)
    assert len(path["relations"]) == 2
    assert {item["chunk_id"] for item in path["evidence"]} == {"a", "b", "c"}
    risk = next(
        relation for relation in path["relations"] if relation["predicate"] == "RISK_FACTOR_FOR"
    )
    assert risk["subject"] == "gamma" and risk["object"] == "beta"
    assert path["inference"] == "navigation_only_no_transitive_claim"
    assert {item.metadata["chunk_id"] for item in found} == {"a", "b", "c"}


def test_stale_evidence_cannot_load(graph_corpus):
    """Không dùng evidence của chunk hoặc phiên bản đã hết hiệu lực."""
    _, rows, ontology, annotations, _ = graph_corpus
    data = build_graph_data(rows, ontology, annotations)
    data["evidence"][0]["chunk_id"] = "deleted"
    with pytest.raises(ValueError, match="Evidence"):
        KnowledgeGraph(data, rows)


def test_entity_linking_longest_alias_and_original_query_expansion():
    """Giữ riêng típ 1/2 và truy vấn gốc, tránh ánh xạ chung che thực thể cụ thể."""
    from backend.core.config import ROOT

    ontology = json.loads((ROOT / "data/knowledge/ontology.json").read_text(encoding="utf-8"))
    linked = link_entities("Tiểu đường típ 2 và HbA1c", ontology["entities"])
    assert {item["entity_id"] for item in linked} == {"type_2_diabetes", "a1c_test"}
    tokens = expand_query("kháng insulin", ontology["entities"])
    assert "khang" in tokens and "resistance" in tokens
    assert link_entities("típ 1 hay típ 2", ontology["entities"]) == []


def test_bm25_does_not_forge_cosine_distance(graph_corpus):
    """Ứng viên keyword có điểm riêng và không bị giả thành khoảng cách vector."""
    _, rows, ontology, _, _ = graph_corpus
    found = LexicalIndex(rows, ontology["entities"]).search("Gamma", 5)
    assert found[0].metadata["chunk_id"] == "b"
    assert found[0].distance is None and found[0].channels == ["bm25"]


def test_rrf_deduplicates_ids_and_does_not_sum_raw_scores():
    """Thang điểm đầu vào không làm đổi RRF; một ID chỉ tính một lần mỗi nhánh."""
    first = Evidence("A", {"chunk_id": "a"}, 0.1, ["vector"], 1000)
    second = Evidence("B", {"chunk_id": "b"}, None, ["bm25"], 1)
    repeated = Evidence("A", {"chunk_id": "a"}, None, ["graph"], -500)
    result = reciprocal_rank_fusion([[first, second], [repeated, repeated]], 60)
    assert len(result) == 2 and result[0].metadata["chunk_id"] == "a"
    assert result[0].score == pytest.approx(2 / 61)
    assert set(result[0].channels) == {"vector", "graph"}
    assert result[0].distance == 0.1


def test_snapshot_activation_is_repeatable_without_embedding(graph_corpus):
    """Cùng dữ liệu tạo cùng snapshot, graph/BM25 trỏ đúng collection và không gọi API."""
    settings, _, ontology, annotations, store = graph_corpus
    first = build_snapshot(settings, store, ontology, annotations, activate=True)
    second = build_snapshot(settings, store, ontology, annotations, activate=True)
    assert first == second and first["embedding_requests"] == 0
    loaded = load_active_snapshot(settings)
    assert loaded.corpus_version == fingerprint(collection_rows(store.collection))


def test_graph_adds_evidence_outside_vector_and_records_trace(graph_corpus):
    """Graph thực sự đưa chunk có vector xa vào ứng viên, không chỉ vẽ sơ đồ."""
    settings, _, ontology, annotations, store = graph_corpus
    build_snapshot(settings, store, ontology, annotations, activate=True)
    embeddings = Mock()
    embeddings.embed.return_value = [[1.0] + [0.0] * 767]
    result = Retriever(settings, embeddings, store).retrieve_with_trace("Alpha Gamma", k=3)
    assert {item.metadata["chunk_id"] for item in result.documents} == {"a", "b", "c"}
    assert result.trace["channel_counts"]["vector"] == 1
    assert result.trace["channel_counts"]["graph"] == 3
    assert any(path["hops"] == 2 for path in result.trace["graph"]["paths"])


def test_snapshot_tampering_falls_back_without_mixing_versions(graph_corpus):
    """Checksum sai làm tắt các nhánh mới, giữ nhánh vector và báo lý do trong trace."""
    settings, _, ontology, annotations, store = graph_corpus
    report = build_snapshot(settings, store, ontology, annotations, activate=True)
    graph_file = settings.retrieval_index_dir / "snapshots" / report["snapshot_id"] / "graph.json"
    graph_file.write_text("{}", encoding="utf-8")
    embeddings = Mock()
    embeddings.embed.return_value = [[1.0] + [0.0] * 767]
    result = Retriever(settings, embeddings, store).retrieve_with_trace("Alpha", k=3)
    assert [item.metadata["chunk_id"] for item in result.documents] == ["a"]
    assert "snapshot_unavailable_using_vector" in result.trace["warnings"]


def test_failed_build_does_not_publish_new_pointer(graph_corpus):
    """Graph sai không được ghi đè con trỏ active đang hoạt động."""
    settings, _, ontology, annotations, store = graph_corpus
    build_snapshot(settings, store, ontology, annotations, activate=True)
    before = (settings.retrieval_index_dir / "active.json").read_bytes()
    bad = [{**annotations[0], "quote": "not in source"}]
    with pytest.raises(ValueError):
        build_snapshot(settings, store, ontology, bad, activate=True)
    assert (settings.retrieval_index_dir / "active.json").read_bytes() == before


def test_wiki_cannot_supply_clinical_recommendations():
    """Wiki chỉ hỗ trợ định nghĩa; bật wiki không cho phép dùng làm nguồn điều trị."""
    wiki = {"source_provider": "wikipedia"}
    assert source_allowed(wiki, "Insulin resistance là gì?", True)
    assert not source_allowed(wiki, "Insulin resistance là gì? Tôi nên dùng thuốc nào?", True)
    assert not source_allowed(wiki, "A1C là gì?", False)


def test_changed_chroma_cannot_mix_with_old_graph(graph_corpus):
    """Corpus Chroma đổi mà chưa build snapshot phải tắt graph/BM25 cho yêu cầu đó."""
    settings, _, ontology, annotations, store = graph_corpus
    build_snapshot(settings, store, ontology, annotations, activate=True)
    store.collection.update(
        ids=["a"], documents=["Changed software text."], embeddings=[[1.0] + [0.0] * 767]
    )
    embeddings = Mock()
    embeddings.embed.return_value = [[1.0] + [0.0] * 767]
    result = Retriever(settings, embeddings, store).retrieve_with_trace("Alpha Gamma")
    assert "snapshot_unavailable_using_vector" in result.trace["warnings"]
    assert result.trace["mode"] == "vector" and result.documents[0].text == "Changed software text."


def test_local_graph_can_fallback_when_embedding_api_fails(graph_corpus):
    """Snapshot hợp lệ còn cho phép tìm evidence local khi Gemini embedding tạm lỗi."""
    from backend.core.errors import ServiceError

    settings, _, ontology, annotations, store = graph_corpus
    build_snapshot(settings, store, ontology, annotations, activate=True)
    embeddings = Mock()
    embeddings.embed.side_effect = ServiceError("Unavailable", "embedding_unavailable")
    result = Retriever(settings, embeddings, store).retrieve_with_trace("Alpha Gamma")
    assert result.documents and result.trace["channel_counts"]["graph"] == 3
    assert "vector_unavailable_using_local_indexes" in result.trace["warnings"]


def test_rrf_rejects_same_id_with_conflicting_content():
    """Không hợp nhất chunk cùng ID đến từ hai corpus có nội dung khác nhau."""
    with pytest.raises(ValueError, match="khác nội dung"):
        reciprocal_rank_fusion(
            [[Evidence("A", {"chunk_id": "a"})], [Evidence("Changed", {"chunk_id": "a"})]]
        )
