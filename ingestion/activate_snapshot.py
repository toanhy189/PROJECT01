"""Kích hoạt hoặc khôi phục một snapshot đã kiểm chứng, không index lại."""

import argparse
import json

from backend.core.config import Settings, get_settings
from backend.rag.corpus import atomic_json
from backend.rag.snapshot import load_snapshot


def activate_snapshot(settings: Settings, snapshot_id: str) -> dict:
    """Xác minh corpus/Chroma/Neo4j trước khi đổi con trỏ active nguyên tử."""
    snapshot = load_snapshot(settings.retrieval_index_dir, snapshot_id, settings)
    if settings.graph_backend == "neo4j":
        from ingestion.migrate_neo4j import migrate_snapshot

        migrate_snapshot(settings, snapshot_id)
    atomic_json(settings.retrieval_index_dir / "active.json", {"snapshot_id": snapshot_id})
    return {
        "snapshot_id": snapshot_id,
        "collection": snapshot.store.collection.name,
        "chunks": len(snapshot.rows),
        "embedding_requests": 0,
        "note": (
            "Đặt CHROMA_COLLECTION tương ứng trong .env và khởi động lại API "
            "để nhánh fallback dùng đúng corpus."
        ),
    }


def main() -> None:
    """Không xóa collection, snapshot hoặc dữ liệu Neo4j khi chuyển phiên bản."""
    parser = argparse.ArgumentParser(description="Chọn snapshot đã kiểm chứng")
    parser.add_argument("snapshot_id")
    args = parser.parse_args()
    print(json.dumps(activate_snapshot(get_settings(), args.snapshot_id), ensure_ascii=False))


if __name__ == "__main__":
    main()
