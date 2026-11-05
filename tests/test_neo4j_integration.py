"""Kiểm thử database Neo4j thật; chỉ chạy khi NEO4J_INTEGRATION=1."""

import os
from unittest.mock import Mock

import pytest
from fastapi.testclient import TestClient

from backend.agents.nodes import Agents
from backend.core.config import get_settings
from backend.core.errors import ServiceError
from backend.graph.workflow import get_workflow
from backend.main import create_app
from backend.rag.neo4j_connection import close_connections, get_connection
from backend.rag.retriever import Retriever
from backend.rag.snapshot import load_active_snapshot
from ingestion.build_retrieval_indexes import build_snapshot
from ingestion.migrate_neo4j import migrate_snapshot

pytestmark = [
    pytest.mark.neo4j_integration,
    pytest.mark.skipif(
        os.getenv("NEO4J_INTEGRATION") != "1",
        reason="Requires a real running Neo4j; set NEO4J_INTEGRATION=1",
    ),
]


@pytest.fixture
def neo4j_snapshot(graph_corpus, request):
    """Tạo phiên bản corpus test riêng và chỉ dọn các node của phiên bản đó."""
    settings, rows, ontology, annotations, store = graph_corpus
    for annotation in annotations:
        if annotation["subject"] == "alpha":
            annotation.update(getattr(request, "param", {}))
    # Tên thư mục test là duy nhất; thêm vào metadata để tách khỏi mọi snapshot khác.
    for row in rows:
        row["metadata"]["test_run_id"] = str(settings.retrieval_index_dir)
    store.collection.update(
        ids=[row["chunk_id"] for row in rows], metadatas=[row["metadata"] for row in rows]
    )
    live = get_settings()
    cfg = settings.model_copy(
        update={
            "graph_backend": "neo4j",
            "neo4j_uri": live.neo4j_uri,
            "neo4j_user": live.neo4j_user,
            "neo4j_password": live.neo4j_password,
            "neo4j_database": live.neo4j_database,
        }
    )
    report = build_snapshot(cfg, store, ontology, annotations, activate=True)
    sid = report["snapshot_id"]
    production = load_active_snapshot(live).snapshot_id
    assert sid != production
    try:
        yield cfg, store, report, rows, ontology, annotations
    finally:
        # Không xóa toàn database; chỉ phiên bản test đã xác nhận khác corpus thật.
        connection = get_connection(cfg)
        connection.transaction(
            lambda tx: tx.run(
                "MATCH (n {snapshot_id:$sid}) DETACH DELETE n",
                sid=sid,
            ).consume(),
            write=True,
        )
        close_connections()


def test_real_migration_is_idempotent_and_preserves_provenance(neo4j_snapshot):
    """Chạy lại migration thật không tăng node, cạnh hoặc evidence."""
    cfg, _, report, *_ = neo4j_snapshot
    repeated = migrate_snapshot(cfg, report["snapshot_id"])
    assert repeated["idempotent"] and repeated["provenance_verified"]
    assert repeated["counts"] == {
        "Entity": 3,
        "RelationFact": 2,
        "Evidence": 3,
        "Chunk": 3,
        "Document": 3,
    }
    assert repeated["embedding_requests"] == 0


@pytest.mark.parametrize("hops", [1, 2])
def test_real_cypher_matches_networkx(neo4j_snapshot, hops):
    """Hai backend trả cùng candidate và đường đi, kể cả khi duyệt ngược cạnh."""
    cfg, *_ = neo4j_snapshot
    neo = load_active_snapshot(cfg).graph
    old = load_active_snapshot(cfg.model_copy(update={"graph_backend": "networkx"})).graph
    actual, trace = neo.search("an pha Gamma", max_hops=hops)
    expected, old_trace = old.search("an pha Gamma", max_hops=hops)
    assert [item.metadata["chunk_id"] for item in actual] == [
        item.metadata["chunk_id"] for item in expected
    ]
    assert trace["paths"] == old_trace["paths"]
    assert trace["connected"] is True and trace["backend"] == "neo4j"


def test_real_knowledge_agent_uses_neo4j_context(neo4j_snapshot):
    """Embedding mock chỉ cho corpus test; graph và provenance dùng database thật."""
    cfg, store, *_ = neo4j_snapshot
    embedding = Mock()
    embedding.embed.return_value = [[1.0] + [0.0] * 767]
    state = Agents(cfg, None, Retriever(cfg, embedding, store), None).knowledge(
        {"user_query": "Alpha Gamma"}
    )
    trace = state["retrieval_trace"]
    assert trace["graph"]["connected"] and trace["context_chunk_ids"]
    assert any(path["used_in_context"] for path in trace["graph"]["paths"])
    assert {citation.chunk_id for citation in state["citations"]} == {"a", "b", "c"}


def test_real_stats_and_retrieve_api(neo4j_snapshot):
    """HTTP gọi Neo4j thật; Safety vẫn chặn trước khi truy xuất yêu cầu liều thuốc."""
    cfg, store, *_ = neo4j_snapshot
    embedding = Mock()
    embedding.embed.return_value = [[1.0] + [0.0] * 767]
    app = create_app()
    app.dependency_overrides[get_workflow] = lambda: Mock(
        retriever=Retriever(cfg, embedding, store)
    )
    with TestClient(app) as client:
        assert client.get("/api/v1/graph/stats").json()["counts"]["Evidence"] == 3
        result = client.post("/api/v1/retrieve", json={"user_query": "Alpha Gamma"}).json()
        assert result["trace"]["graph"]["connected"]
        blocked = client.post(
            "/api/v1/retrieve", json={"user_query": "Tiêm insulin bao nhiêu đơn vị?"}
        ).json()
        assert blocked["trace"]["safety"] == "blocked"


def test_real_modified_quote_is_rejected(neo4j_snapshot):
    """Database bị sửa quote không được vượt qua đối chiếu snapshot nguồn."""
    cfg, _, report, *_ = neo4j_snapshot
    connection = get_connection(cfg)
    connection.transaction(
        lambda tx: tx.run(
            "MATCH (e:Evidence {snapshot_id:$sid}) SET e.quote='invalid-source-quote'",
            sid=report["snapshot_id"],
        ).consume(),
        write=True,
    )
    with pytest.raises(ServiceError, match="Evidence"):
        load_active_snapshot(cfg).graph.search("Alpha Gamma")
    with pytest.raises(ValueError, match="node"):
        migrate_snapshot(cfg, report["snapshot_id"])


def test_real_wrong_authentication_is_reported(neo4j_snapshot):
    """Đăng nhập sai database thật có mã lỗi riêng và không lộ mật khẩu."""
    cfg, *_ = neo4j_snapshot
    wrong = cfg.model_copy(update={"neo4j_password": "intentionally-wrong-integration-password"})
    with pytest.raises(ServiceError) as captured:
        get_connection(wrong).read("RETURN 1")
    assert captured.value.code == "neo4j_auth_failed"


def test_real_unreachable_port_falls_back(neo4j_snapshot):
    """Cổng không có database thật phải trả vector/BM25 thay vì giả trạng thái graph."""
    cfg, store, *_ = neo4j_snapshot
    down = cfg.model_copy(
        update={"neo4j_uri": "bolt://127.0.0.1:1", "neo4j_connection_timeout_seconds": 0.1}
    )
    embedding = Mock()
    embedding.embed.return_value = [[1.0] + [0.0] * 767]
    result = Retriever(down, embedding, store).retrieve_with_trace("Alpha Gamma")
    assert result.documents and result.trace["graph"]["status"] == "fallback"
    assert result.trace["graph"]["connected"] is False


def test_real_missing_snapshot_does_not_mix_versions(neo4j_snapshot):
    """Header phiên bản sai làm bỏ nhánh graph, không dùng graph snapshot khác."""
    cfg, _, report, *_ = neo4j_snapshot
    connection = get_connection(cfg)
    connection.transaction(
        lambda tx: tx.run(
            "MATCH (s:GraphSnapshot {snapshot_id:$sid}) SET s.graph_hash='wrong-version'",
            sid=report["snapshot_id"],
        ).consume(),
        write=True,
    )
    with pytest.raises(ServiceError) as captured:
        load_active_snapshot(cfg).graph.search("Alpha Gamma")
    assert captured.value.code == "neo4j_snapshot_mismatch"


@pytest.mark.parametrize(
    "neo4j_snapshot",
    [
        {"polarity": "negative", "qualifiers": "Only this software test condition"},
    ],
    indirect=True,
)
def test_real_negation_and_condition_are_preserved(neo4j_snapshot):
    """Phủ định và điều kiện không biến mất khi import rồi truy vấn database thật."""
    cfg, *_ = neo4j_snapshot
    _, trace = load_active_snapshot(cfg).graph.search("Alpha Gamma")
    facts = [
        fact for path in trace["paths"] for fact in path["relations"] if fact["subject"] == "alpha"
    ]
    assert facts and all(fact["polarity"] == "negative" for fact in facts)
    assert all(fact["qualifiers"] == "Only this software test condition" for fact in facts)


def test_real_missing_evidence_cannot_be_used(neo4j_snapshot):
    """Cạnh mất liên kết chứng cứ không được đưa vào context."""
    cfg, _, report, *_ = neo4j_snapshot
    connection = get_connection(cfg)
    connection.transaction(
        lambda tx: tx.run(
            "MATCH (f:RelationFact {snapshot_id:$sid})-[r:SUPPORTED_BY]->() DELETE r",
            sid=report["snapshot_id"],
        ).consume(),
        write=True,
    )
    with pytest.raises(ServiceError) as captured:
        load_active_snapshot(cfg).graph.search("Alpha Gamma")
    assert captured.value.code == "neo4j_invalid_evidence"


def test_real_transaction_timeout_is_enforced(neo4j_snapshot):
    """Server hủy truy vấn tính toán dài theo giới hạn transaction thực tế."""
    cfg, *_ = neo4j_snapshot
    bounded = cfg.model_copy(update={"neo4j_query_timeout_seconds": 0.1})
    with pytest.raises(ServiceError) as captured:
        get_connection(bounded).read(
            "UNWIND range(1, 100000000) AS i WITH i WHERE i >= 0 RETURN sum(i) AS total"
        )
    assert captured.value.code == "neo4j_unavailable"


def test_real_new_version_preserves_old_graph(neo4j_snapshot):
    """Thêm graph phiên bản mới không ghi đè fact hoặc evidence của snapshot cũ."""
    from backend.rag.snapshot import load_snapshot

    cfg, store, old, _, ontology, annotations = neo4j_snapshot
    changed = [{**item, "qualifiers": "New version condition"} for item in annotations]
    new = build_snapshot(cfg, store, ontology, changed, activate=False)
    assert new["snapshot_id"] != old["snapshot_id"]
    migrate_snapshot(cfg, new["snapshot_id"])
    try:
        old_graph = load_active_snapshot(cfg).graph
        new_graph = load_snapshot(cfg.retrieval_index_dir, new["snapshot_id"], cfg).graph
        assert all(not fact.qualifiers for fact in old_graph.relations.values())
        _, trace = new_graph.search("Alpha Gamma")
        assert all(
            fact["qualifiers"] == "New version condition"
            for path in trace["paths"]
            for fact in path["relations"]
        )
        assert migrate_snapshot(cfg, old["snapshot_id"])["idempotent"]
    finally:
        get_connection(cfg).transaction(
            lambda tx: tx.run(
                "MATCH (n {snapshot_id:$sid}) DETACH DELETE n",
                sid=new["snapshot_id"],
            ).consume(),
            write=True,
        )
