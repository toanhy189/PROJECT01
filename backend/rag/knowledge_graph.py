"""Knowledge Graph có hướng, evidence riêng và truy xuất giới hạn hai bước."""

import re
from collections import defaultdict
from typing import Literal

import networkx as nx
from pydantic import BaseModel, ConfigDict, Field

from backend.rag.corpus import document_versions, fingerprint, provider
from backend.rag.graph_search import make_path, rank_paths
from backend.rag.lexical import link_entities, normalize_term
from backend.rag.models import Evidence

ENTITY_TYPES = {"condition", "symptom", "risk_factor", "test", "concept", "prevention", "organ"}
RELATION_TYPES = {
    "HAS_SUBTYPE",
    "HAS_ASSOCIATED_SYMPTOM",
    "RISK_FACTOR_FOR",
    "ASSOCIATED_WITH",
    "USED_TO_ASSESS",
    "MEASURES",
    "MAY_REDUCE_RISK_OF",
    "CANNOT_DIAGNOSE",
    "PRODUCES",
}
INTENT_RULES = {
    "RISK_FACTOR_FOR": r"nguy co|risk|gia dinh|it van dong|thua can|beo phi",
    "HAS_ASSOCIATED_SYMPTOM": r"trieu chung|symptom|dau hieu",
    "USED_TO_ASSESS": r"xet nghiem|test|chan doan|danh gia|detect|assess",
    "CANNOT_DIAGNOSE": r"tu chan doan|may do|meter|cannot|khong the",
    "MEASURES": r"do luong|phan anh|trung binh|measure|average|bao lau|a1c|hba1c",
    "MAY_REDUCE_RISK_OF": r"phong ngua|ngan ngua|tri hoan|prevent|delay|loi song|giam can",
    "HAS_SUBTYPE": r"phan loai|nhung loai|types|khac nhau",
}


class Entity(BaseModel):
    """Thực thể chuẩn hóa với tên và bí danh có kiểm soát."""

    model_config = ConfigDict(extra="forbid")
    entity_id: str
    name: str
    entity_type: str
    aliases: list[str] = Field(default_factory=list)


class Relation(BaseModel):
    """Quan hệ có hướng; không mặc định có tính đối xứng hoặc bắc cầu."""

    model_config = ConfigDict(extra="forbid")
    relation_id: str
    subject: str
    predicate: str
    object: str
    polarity: Literal["positive", "negative", "uncertain"] = "positive"
    qualifiers: str = ""


class RelationEvidence(BaseModel):
    """Một nguồn chứng minh riêng, không ghi đè bằng chứng từ nguồn khác."""

    model_config = ConfigDict(extra="forbid")
    evidence_id: str
    relation_id: str
    document_id: str
    chunk_id: str
    content_version: str
    source_url: str
    source_provider: str
    quote: str = Field(min_length=3)
    status: Literal["source_checked", "human_reviewed"]
    checked_by: str = Field(min_length=1)


def build_graph_data(rows: list[dict], ontology: dict, annotations: list[dict]) -> dict:
    """Biên dịch các annotation đã kiểm tra nguồn, từ chối quote/phiên bản không khớp."""
    entities = [Entity.model_validate(item) for item in ontology["entities"]]
    if len({e.entity_id for e in entities}) != len(entities):
        raise ValueError("Trùng entity ID trong ontology.")
    if any(e.entity_type not in ENTITY_TYPES for e in entities):
        raise ValueError("Loại thực thể không được duyệt.")
    entity_ids = {entity.entity_id for entity in entities}
    versions = document_versions(rows)
    relations, evidence = {}, {}
    for annotation in annotations:
        if annotation.get("status") not in {"source_checked", "human_reviewed"}:
            continue
        if not annotation.get("checked_by") or annotation["predicate"] not in RELATION_TYPES:
            raise ValueError("Annotation chưa xác định người kiểm tra hoặc loại quan hệ.")
        if annotation["subject"] not in entity_ids or annotation["object"] not in entity_ids:
            raise ValueError("Quan hệ trỏ đến thực thể không tồn tại.")
        qualifiers = annotation.get("qualifiers", "")
        identity = {key: annotation[key] for key in ("subject", "predicate", "object")}
        identity.update(polarity=annotation.get("polarity", "positive"), qualifiers=qualifiers)
        rid = fingerprint(identity)[:24]
        relation = Relation(relation_id=rid, **identity)
        matching = [
            row
            for row in rows
            if row["metadata"]["document_id"] == annotation["document_id"]
            and annotation["quote"] in row["text"]
        ]
        if not matching:
            # Corpus mở rộng có thể không chứa một phần annotation của corpus khác.
            if annotation["document_id"] not in versions:
                continue
            raise ValueError(
                f"Quote graph không có trong chunk hiện tại: {annotation['document_id']}"
            )
        relations[rid] = relation.model_dump()
        for row in matching:
            if provider(row["metadata"]) == "wikipedia" and annotation["predicate"] not in {
                "HAS_SUBTYPE",
                "MEASURES",
                "PRODUCES",
            }:
                raise ValueError(
                    "Wiki chỉ được bổ sung quan hệ kiến thức nền, không làm nguồn khuyến nghị y khoa."
                )
            eid = fingerprint([rid, row["chunk_id"], annotation["quote"]])[:24]
            evidence[eid] = RelationEvidence(
                evidence_id=eid,
                relation_id=rid,
                document_id=annotation["document_id"],
                chunk_id=row["chunk_id"],
                content_version=versions[annotation["document_id"]],
                source_url=row["metadata"]["source_url"],
                source_provider=provider(row["metadata"]),
                quote=annotation["quote"],
                status=annotation["status"],
                checked_by=annotation["checked_by"],
            ).model_dump()
    return {
        "schema_version": 1,
        "corpus_version": fingerprint(rows),
        "entities": [entity.model_dump() for entity in entities],
        "relations": sorted(relations.values(), key=lambda item: item["relation_id"]),
        "evidence": sorted(evidence.values(), key=lambda item: item["evidence_id"]),
    }


class ValidatedGraph:
    """Kiểm tra dữ liệu và provenance độc lập với backend graph."""

    def __init__(self, data: dict, rows: list[dict]) -> None:
        """Kiểm tra graph và corpus cùng phiên bản trước khi cho phép truy xuất."""
        if data.get("schema_version") != 1:
            raise ValueError("Phiên bản schema graph chưa được hỗ trợ.")
        if data["corpus_version"] != fingerprint(rows):
            raise ValueError("Graph không cùng phiên bản corpus.")
        self.corpus_version = data["corpus_version"]
        self.rows = {row["chunk_id"]: row for row in rows}
        self.entities = [Entity.model_validate(item).model_dump() for item in data["entities"]]
        entity_ids = {entity["entity_id"] for entity in self.entities}
        if len(entity_ids) != len(self.entities):
            raise ValueError("Trùng entity ID.")
        if any(entity["entity_type"] not in ENTITY_TYPES for entity in self.entities):
            raise ValueError("Loại thực thể không được duyệt.")
        self.relations = {r.relation_id: r for r in map(Relation.model_validate, data["relations"])}
        if len(self.relations) != len(data["relations"]):
            raise ValueError("Trùng relation ID.")
        self.evidence: dict[str, list[dict]] = defaultdict(list)
        evidence_ids = set()
        versions = document_versions(rows)
        for raw in data["evidence"]:
            item = RelationEvidence.model_validate(raw)
            row = self.rows.get(item.chunk_id)
            if (
                row is None
                or item.evidence_id in evidence_ids
                or item.relation_id not in self.relations
                or item.quote not in row["text"]
                or item.document_id != row["metadata"]["document_id"]
                or item.content_version != versions[item.document_id]
                or item.source_url != row["metadata"]["source_url"]
                or item.source_provider != provider(row["metadata"])
                or item.status not in {"source_checked", "human_reviewed"}
            ):
                raise ValueError("Evidence graph không hợp lệ hoặc đã hết hiệu lực.")
            evidence_ids.add(item.evidence_id)
            self.evidence[item.relation_id].append(item.model_dump())
        for rid, relation in self.relations.items():
            if relation.predicate not in RELATION_TYPES or not self.evidence[rid]:
                raise ValueError("Quan hệ không có bằng chứng đã kiểm tra.")
            if relation.subject not in entity_ids or relation.object not in entity_ids:
                raise ValueError("Quan hệ trỏ đến thực thể bị thiếu.")


class KnowledgeGraph(ValidatedGraph):
    """Backend cũ dùng để đối chiếu và rollback khi chọn rõ NetworkX."""

    def __init__(self, data: dict, rows: list[dict]) -> None:
        """Chỉ dựng NetworkX khi backend cũ được chọn."""
        super().__init__(data, rows)
        self.graph = nx.MultiDiGraph()
        for entity in self.entities:
            self.graph.add_node(entity["entity_id"], **entity)
        for rid, relation in self.relations.items():
            self.graph.add_edge(relation.subject, relation.object, key=rid, relation_id=rid)

    def search(
        self, question: str, limit: int = 15, max_hops: int = 2, max_paths: int = 40
    ) -> tuple[list[Evidence], dict]:
        """Xếp hạng đường đi bằng khớp thực thể/ý định, số bước và chất lượng nguồn."""
        linked = link_entities(question, self.entities)
        starts = {item["entity_id"] for item in linked}
        intents = {
            key
            for key, pattern in INTENT_RULES.items()
            if re.search(pattern, normalize_term(question))
        }
        if len(starts) < 2 and not intents:
            return [], {
                "linked_entities": linked,
                "paths": [],
                "reason": "no_relation_intent",
                "ranking_policy": "relation_intent_required",
            }
        paths = []
        # Có thể đi ngược cạnh để tìm nguồn, nhưng vẫn giữ hướng quan hệ gốc trong trace.
        for start in sorted(starts):
            queue = [([start], [])]
            while queue and len(paths) < max_paths * 10:
                nodes, edges = queue.pop(0)
                if len(edges) >= min(max_hops, 2):
                    continue
                neighbors = sorted(
                    set(self.graph.successors(nodes[-1])) | set(self.graph.predecessors(nodes[-1]))
                )
                for neighbor in neighbors:
                    if neighbor in nodes:
                        continue
                    pairs = list(self.graph.get_edge_data(nodes[-1], neighbor, default={}))
                    pairs += list(self.graph.get_edge_data(neighbor, nodes[-1], default={}))
                    for rid in sorted(set(pairs)):
                        new_nodes, new_edges = nodes + [neighbor], edges + [rid]
                        ev = [item for edge in new_edges for item in self.evidence[edge]]
                        matched = len(starts & set(new_nodes))
                        intent_matches = sum(
                            self.relations[e].predicate in intents for e in new_edges
                        )
                        queue.append((new_nodes, new_edges))
                        if not intent_matches and matched < 2:
                            continue
                        paths.append(
                            make_path(
                                new_nodes,
                                [self.relations[e].model_dump() for e in new_edges],
                                ev,
                                starts,
                                intents,
                            )
                        )
        return rank_paths(
            paths,
            self.rows,
            limit,
            max_paths,
            {
                "linked_entities": linked,
                "backend": "networkx",
                "status": "ok",
                "relation_count": len(self.relations),
                "evidence_count": sum(map(len, self.evidence.values())),
            },
        )
