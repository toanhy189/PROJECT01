"""Ánh xạ snapshot sang property graph có phiên bản, giữ nguyên ID và provenance."""

from backend.rag.corpus import document_versions, fingerprint, provider
from backend.rag.knowledge_graph import ValidatedGraph

LABEL_KEYS = {
    "Entity": "entity_id",
    "RelationFact": "relation_id",
    "Evidence": "evidence_id",
    "Chunk": "chunk_id",
    "Document": "document_id",
}


def node_uid(snapshot_id: str, label: str, logical_id: str) -> str:
    """Tách ID vật lý theo phiên bản, không thay ID mà Chroma và citations đang dùng."""
    return fingerprint([snapshot_id, label, logical_id])


def graph_payload(snapshot_id: str, data: dict, rows: list[dict]) -> dict[str, list[dict]]:
    """Chỉ nhận snapshot đã kiểm tra quote, chunk, URL và phiên bản nguồn."""
    ValidatedGraph(data, rows)
    versions = document_versions(rows)
    documents = {}
    chunks = []
    for row in rows:
        meta = row["metadata"]
        did = meta["document_id"]
        document = {
            key: meta[key]
            for key in (
                "document_id",
                "title",
                "source_url",
                "language",
                "revision_id",
                "retrieved_at",
                "license",
                "license_url",
                "attribution_url",
                "section_scope",
                "changes",
            )
            if key in meta
        }
        document.update(content_version=versions[did], source_provider=provider(meta))
        if did in documents and documents[did] != document:
            raise ValueError("Metadata nguồn không thống nhất giữa các chunk.")
        documents[did] = document
        chunks.append(
            {
                "chunk_id": row["chunk_id"],
                "document_id": did,
                "content_hash": fingerprint(row["text"]),
                **{
                    key: meta[key]
                    for key in ("section", "section_path", "page_number")
                    if key in meta
                },
            }
        )
    payload = {
        "Entity": data["entities"],
        "RelationFact": data["relations"],
        "Evidence": data["evidence"],
        "Chunk": chunks,
        "Document": list(documents.values()),
    }
    return {
        label: sorted(
            [
                {
                    **{key: value for key, value in item.items() if value is not None},
                    "snapshot_id": snapshot_id,
                    "uid": node_uid(snapshot_id, label, item[LABEL_KEYS[label]]),
                }
                for item in items
            ],
            key=lambda item: item["uid"],
        )
        for label, items in payload.items()
    }


def expected_links(payload: dict[str, list[dict]]) -> list[dict]:
    """Định danh mọi cạnh cấu trúc để kiểm tra cả đường chứng cứ sau migration."""
    sid = next(item["snapshot_id"] for items in payload.values() for item in items)

    def link(kind: str, left: str, left_id: str, right: str, right_id: str) -> dict:
        """Chỉ ánh xạ các loại cạnh do code kiểm soát."""
        return {
            "kind": kind,
            "left": node_uid(sid, left, left_id),
            "right": node_uid(sid, right, right_id),
        }

    links = []
    for fact in payload["RelationFact"]:
        for kind, key in (("SUBJECT", "subject"), ("OBJECT", "object")):
            links.append(link(kind, "RelationFact", fact["relation_id"], "Entity", fact[key]))
    for item in payload["Evidence"]:
        links.append(
            link(
                "SUPPORTED_BY", "RelationFact", item["relation_id"], "Evidence", item["evidence_id"]
            )
        )
        links.append(link("FROM_CHUNK", "Evidence", item["evidence_id"], "Chunk", item["chunk_id"]))
    for item in payload["Chunk"]:
        links.append(
            link("FROM_DOCUMENT", "Chunk", item["chunk_id"], "Document", item["document_id"])
        )
    return sorted(links, key=lambda item: (item["kind"], item["left"], item["right"]))
