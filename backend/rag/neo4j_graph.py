"""Truy xuất đường đi thật bằng Cypher, dùng lại chính sách xếp hạng của Custom RAG."""

import re
import time

from backend.core.config import Settings
from backend.core.errors import ServiceError
from backend.rag.graph_search import make_path, rank_paths
from backend.rag.knowledge_graph import INTENT_RULES, Relation, RelationEvidence, ValidatedGraph
from backend.rag.lexical import link_entities, normalize_term
from backend.rag.models import Evidence
from backend.rag.neo4j_connection import get_connection
from backend.rag.neo4j_schema import node_uid

# Hai cạnh SUBJECT/OBJECT tương ứng một bước quan hệ y khoa, không phải hai bước.
PATH_QUERY = """
UNWIND $start_uids AS start_uid
MATCH (start:Entity {uid:start_uid})
CALL (start) {
    MATCH (start)<-[:SUBJECT|OBJECT]-(f1:RelationFact)-[:SUBJECT|OBJECT]->(middle:Entity)
    WHERE middle <> start AND f1.snapshot_id=$sid AND middle.snapshot_id=$sid
    RETURN [start.entity_id,middle.entity_id] AS nodes, [f1.relation_id] AS relation_ids
    UNION ALL
    MATCH (start)<-[:SUBJECT|OBJECT]-(f1:RelationFact)-[:SUBJECT|OBJECT]->(middle:Entity)
    WHERE $max_hops=2 AND middle <> start AND f1.snapshot_id=$sid
      AND middle.snapshot_id=$sid
    WITH start, middle, f1 ORDER BY middle.entity_id, f1.relation_id LIMIT $budget
    MATCH (middle)<-[:SUBJECT|OBJECT]-(f2:RelationFact)-[:SUBJECT|OBJECT]->(last:Entity)
    WHERE last <> start AND last <> middle AND f2 <> f1
      AND f2.snapshot_id=$sid AND last.snapshot_id=$sid
    RETURN [start.entity_id,middle.entity_id,last.entity_id] AS nodes,
           [f1.relation_id,f2.relation_id] AS relation_ids
}
WITH DISTINCT nodes, relation_ids
ORDER BY nodes, relation_ids LIMIT $budget
RETURN nodes, relation_ids
"""

EVIDENCE_QUERY = """
UNWIND $fact_uids AS fact_uid
MATCH (f:RelationFact {uid:fact_uid})-[:SUPPORTED_BY]->(e:Evidence)
      -[:FROM_CHUNK]->(c:Chunk)-[:FROM_DOCUMENT]->(d:Document)
WHERE e.snapshot_id=$sid AND c.snapshot_id=$sid AND d.snapshot_id=$sid
MATCH (f)-[:SUBJECT]->(subject:Entity), (f)-[:OBJECT]->(object:Entity)
WHERE subject.snapshot_id=$sid AND object.snapshot_id=$sid
RETURN properties(f) AS fact, properties(e) AS evidence,
       properties(c) AS chunk, properties(d) AS document,
       subject.entity_id AS subject_id, object.entity_id AS object_id
ORDER BY f.relation_id, e.evidence_id
LIMIT $evidence_budget
"""


class Neo4jGraph(ValidatedGraph):
    """JSON xác minh nguồn; chỉ đường đi và evidence do Neo4j trả về mới được sử dụng."""

    def __init__(
        self, data: dict, rows: list[dict], settings: Settings, snapshot_id: str, graph_hash: str
    ) -> None:
        """Không mở kết nối khi graph chưa bật hoặc chỉ kiểm tra snapshot local."""
        super().__init__(data, rows)
        self.settings, self.snapshot_id, self.graph_hash = settings, snapshot_id, graph_hash

    def search(
        self, question: str, limit: int = 15, max_hops: int = 2, max_paths: int = 40
    ) -> tuple[list[Evidence], dict]:
        """Truy vấn giới hạn hai bước, xác minh evidence rồi chuyển ứng viên sang fusion."""
        started = time.perf_counter()
        linked = link_entities(question, self.entities)[:8]
        starts = {item["entity_id"] for item in linked}
        intents = {
            key
            for key, pattern in INTENT_RULES.items()
            if re.search(pattern, normalize_term(question))
        }
        trace = {
            "backend": "neo4j",
            "linked_entities": linked,
            "snapshot_id": self.snapshot_id,
            "relation_count": len(self.relations),
            "evidence_count": sum(map(len, self.evidence.values())),
        }
        if not starts or (len(starts) < 2 and not intents):
            return [], {
                **trace,
                "paths": [],
                "status": "no_relation_intent",
                "connected": None,
                "query_count": 0,
                "latency_ms": 0,
            }
        connection = get_connection(self.settings)
        budget = self.settings.graph_expansion_limit
        params = {
            "sid": self.snapshot_id,
            "budget": budget,
            "max_hops": min(max(max_hops, 1), 2),
            "start_uids": [node_uid(self.snapshot_id, "Entity", eid) for eid in sorted(starts)],
        }

        def retrieve(tx) -> tuple[list[dict], list[dict]]:
            """Đọc header và các đường đi trên cùng transaction của snapshot bất biến."""
            header = tx.run(
                connection.query(
                    "MATCH (s:GraphSnapshot {snapshot_id:$sid}) RETURN properties(s) AS props"
                ),
                sid=self.snapshot_id,
            ).single()
            if not header or any(
                header["props"].get(key) != value
                for key, value in {
                    "status": "ready",
                    "corpus_version": self.corpus_version,
                    "graph_hash": self.graph_hash,
                }.items()
            ):
                raise ServiceError(
                    "Neo4j chưa có đúng snapshot đã duyệt.", "neo4j_snapshot_mismatch"
                )
            raw_paths = tx.run(connection.query(PATH_QUERY), params).data()
            rids = {rid for path in raw_paths for rid in path["relation_ids"]}
            if not rids:
                return raw_paths, []
            records = tx.run(
                connection.query(EVIDENCE_QUERY),
                {
                    "sid": self.snapshot_id,
                    "fact_uids": [
                        node_uid(self.snapshot_id, "RelationFact", rid) for rid in sorted(rids)
                    ],
                    "evidence_budget": sum(map(len, self.evidence.values())) + 1,
                },
            ).data()
            return raw_paths, records

        raw_paths, records = connection.transaction(retrieve)
        facts, evidence = self._validate_records(records)
        paths = []
        for raw in raw_paths:
            nodes, rids = raw["nodes"], raw["relation_ids"]
            if any(rid not in facts or not evidence.get(rid) for rid in rids):
                raise ServiceError("Neo4j thiếu evidence cho đường đi.", "neo4j_invalid_evidence")
            if (
                len(nodes) != len(rids) + 1
                or len(set(nodes)) != len(nodes)
                or any(
                    {facts[rid]["subject"], facts[rid]["object"]} != set(nodes[i : i + 2])
                    for i, rid in enumerate(rids)
                )
            ):
                raise ServiceError(
                    "Đường Neo4j sai thực thể hoặc hướng nguồn.", "neo4j_invalid_evidence"
                )
            path = make_path(
                nodes,
                [facts[rid] for rid in rids],
                [ev for rid in rids for ev in evidence[rid]],
                starts,
                intents,
            )
            if path["intent_matches"] or path["matched_query_entities"] >= 2:
                paths.append(path)
        found, trace = rank_paths(
            paths,
            self.rows,
            limit,
            max_paths,
            {
                **trace,
                "status": "ok" if paths else "no_evidence",
                "connected": True,
                "query_count": 3 if records else 2,
                "raw_path_count": len(raw_paths),
                "expansion_limit_reached": len(raw_paths) >= budget,
            },
        )
        trace["latency_ms"] = round((time.perf_counter() - started) * 1000, 3)
        return found, trace

    def _validate_records(self, records: list[dict]) -> tuple[dict, dict]:
        """Từ chối quote, URL, hướng cạnh hoặc chunk bị thay đổi trong database."""
        from backend.rag.corpus import fingerprint

        facts, evidence = {}, {}
        for record in records:
            fact = {
                key: value for key, value in record["fact"].items() if key in Relation.model_fields
            }
            ev = {
                key: value
                for key, value in record["evidence"].items()
                if key in RelationEvidence.model_fields
            }
            rid = fact.get("relation_id")
            if rid not in self.relations or fact != self.relations[rid].model_dump():
                raise ServiceError("Quan hệ Neo4j không khớp nguồn.", "neo4j_invalid_evidence")
            row = self.rows.get(ev.get("chunk_id"))
            if (
                ev not in self.evidence[rid]
                or row is None
                or record["subject_id"] != fact["subject"]
                or record["object_id"] != fact["object"]
                or record["chunk"].get("chunk_id") != ev["chunk_id"]
                or record["chunk"].get("document_id") != ev["document_id"]
                or record["chunk"].get("content_hash") != fingerprint(row["text"])
                or record["document"].get("document_id") != ev["document_id"]
                or record["document"].get("source_url") != ev["source_url"]
                or record["document"].get("content_version") != ev["content_version"]
                or record["document"].get("source_provider") != ev["source_provider"]
            ):
                raise ServiceError("Evidence Neo4j không khớp nguồn.", "neo4j_invalid_evidence")
            facts[rid] = fact
            evidence.setdefault(rid, []).append(ev)
        for rid, items in evidence.items():
            if sorted(items, key=lambda item: item["evidence_id"]) != sorted(
                self.evidence[rid], key=lambda item: item["evidence_id"]
            ):
                raise ServiceError("Neo4j thiếu hoặc lặp evidence.", "neo4j_invalid_evidence")
        return facts, evidence
