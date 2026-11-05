"""Migration snapshot sang Neo4j bằng transaction nguyên tử, không gọi embedding."""

import argparse
import json

from backend.core.config import ROOT, Settings, get_settings
from backend.core.errors import ServiceError
from backend.rag.corpus import atomic_json, fingerprint
from backend.rag.neo4j_connection import close_connections, get_connection
from backend.rag.neo4j_schema import LABEL_KEYS, expected_links, graph_payload
from backend.rag.snapshot import load_snapshot


def verify_payload(tx, connection, sid: str, payload: dict, links: list[dict]) -> None:
    """Đọc lại node và cạnh để phát hiện import thiếu hoặc provenance bị thay đổi."""
    actual = tx.run(
        connection.query(
            "MATCH (n {snapshot_id:$sid}) WHERE n.uid IS NOT NULL "
            "RETURN labels(n) AS labels, properties(n) AS props"
        ),
        sid=sid,
    ).data()
    grouped = {label: [] for label in LABEL_KEYS}
    for item in actual:
        if len(item["labels"]) != 1 or item["labels"][0] not in grouped:
            raise ValueError("Snapshot Neo4j có node không đúng schema.")
        grouped[item["labels"][0]].append(item["props"])
    if any(
        sorted(grouped[label], key=lambda item: item["uid"]) != payload[label] for label in grouped
    ):
        raise ValueError("Dữ liệu node Neo4j khác snapshot nguồn.")
    actual_links = tx.run(
        connection.query(
            "MATCH (a {snapshot_id:$sid})-[r]->(b) "
            "RETURN type(r) AS kind, a.uid AS left, b.uid AS right"
        ),
        sid=sid,
    ).data()
    actual_links = sorted(
        actual_links, key=lambda item: (item["kind"], item["left"], item["right"])
    )
    if actual_links != links:
        raise ValueError("Đường provenance Neo4j khác snapshot nguồn.")


def migrate_snapshot(settings: Settings, snapshot_id: str) -> dict:
    """Chạy lại chỉ kiểm chứng; không ghi đè snapshot đã công bố hoặc xóa dữ liệu."""
    offline = settings.model_copy(update={"graph_backend": "networkx"})
    snapshot = load_snapshot(settings.retrieval_index_dir, snapshot_id, offline)
    directory = settings.retrieval_index_dir / "snapshots" / snapshot_id
    data = json.loads((directory / "graph.json").read_text(encoding="utf-8"))
    manifest = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
    payload = graph_payload(snapshot_id, data, snapshot.rows)
    links = expected_links(payload)
    connection = get_connection(settings)
    for label in LABEL_KEYS:
        # Nhãn chỉ lấy từ danh sách cố định, mọi giá trị dữ liệu đều là tham số.
        connection.transaction(
            lambda tx, label=label: tx.run(
                connection.query(
                    f"CREATE CONSTRAINT glucoguide_{label.lower()}_uid IF NOT EXISTS "
                    f"FOR (n:{label}) REQUIRE n.uid IS UNIQUE"
                )
            ).consume(),
            write=True,
        )
    connection.transaction(
        lambda tx: tx.run(
            connection.query(
                "CREATE CONSTRAINT glucoguide_snapshot_id IF NOT EXISTS "
                "FOR (n:GraphSnapshot) REQUIRE n.snapshot_id IS UNIQUE"
            )
        ).consume(),
        write=True,
    )
    header = {
        "snapshot_id": snapshot_id,
        "corpus_version": snapshot.corpus_version,
        "graph_hash": manifest["graph_hash"],
        "payload_hash": fingerprint(payload),
        "status": "ready",
        "schema_version": 1,
    }

    def import_transaction(tx) -> bool:
        """Công bố ready cùng transaction sau khi kiểm tra đủ mọi bản ghi."""
        found = tx.run(
            connection.query(
                "MATCH (s:GraphSnapshot {snapshot_id:$sid}) RETURN properties(s) AS props"
            ),
            sid=snapshot_id,
        ).data()
        if found:
            if found[0]["props"] != header:
                raise ValueError("Snapshot Neo4j đã tồn tại với checksum hoặc trạng thái khác.")
            verify_payload(tx, connection, snapshot_id, payload, links)
            return False
        tx.run(
            connection.query("CREATE (s:GraphSnapshot) SET s = $props"),
            props={**header, "status": "staging"},
        ).consume()
        for label, items in payload.items():
            tx.run(
                connection.query(
                    f"UNWIND $items AS item MERGE (n:{label} {{uid:item.uid}}) SET n = item"
                ),
                items=items,
            ).consume()
        endpoints = {
            "SUBJECT": ("RelationFact", "Entity"),
            "OBJECT": ("RelationFact", "Entity"),
            "SUPPORTED_BY": ("RelationFact", "Evidence"),
            "FROM_CHUNK": ("Evidence", "Chunk"),
            "FROM_DOCUMENT": ("Chunk", "Document"),
        }
        for kind, (left_label, right_label) in endpoints.items():
            tx.run(
                connection.query(
                    "UNWIND $items AS item "
                    f"MATCH (a:{left_label} {{uid:item.left}}), (b:{right_label} {{uid:item.right}}) "
                    f"MERGE (a)-[:{kind}]->(b)"
                ),
                items=[link for link in links if link["kind"] == kind],
            ).consume()
        verify_payload(tx, connection, snapshot_id, payload, links)
        tx.run(
            connection.query("MATCH (s:GraphSnapshot {snapshot_id:$sid}) SET s.status='ready'"),
            sid=snapshot_id,
        ).consume()
        return True

    created = connection.transaction(import_transaction, write=True)
    return {
        "status": "verified",
        "backend": "neo4j",
        "snapshot_id": snapshot_id,
        "corpus_version": snapshot.corpus_version,
        "created": created,
        "idempotent": not created,
        "counts": {label: len(items) for label, items in payload.items()},
        "structural_relationships": len(links),
        "embedding_requests": 0,
        "provenance_verified": True,
        "chroma_modified": False,
    }


def main() -> None:
    """Ghi báo cáo thành công hoặc lỗi an toàn, không khẳng định database giả lập."""
    parser = argparse.ArgumentParser(description="Migrate verified snapshot to Neo4j")
    parser.add_argument("--snapshot-id")
    args = parser.parse_args()
    settings = get_settings()
    try:
        sid = (
            args.snapshot_id
            or json.loads(
                (settings.retrieval_index_dir / "active.json").read_text(encoding="utf-8")
            )["snapshot_id"]
        )
        report = migrate_snapshot(settings, sid)
    except (OSError, ValueError, KeyError, ServiceError) as exc:
        report = {
            "status": "failed",
            "error_code": getattr(exc, "code", type(exc).__name__),
            "embedding_requests": 0,
            "chroma_modified": False,
        }
        atomic_json(ROOT / "artifacts/neo4j_migration_failed.json", report)
        print(json.dumps(report))
        raise SystemExit(1) from None
    finally:
        close_connections()
    atomic_json(ROOT / "artifacts/neo4j_migration.json", report)
    print(json.dumps(report, ensure_ascii=True, indent=2))


if __name__ == "__main__":
    main()
