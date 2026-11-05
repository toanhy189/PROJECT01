"""Kiểm thử indexing lặp, báo lỗi tài liệu và đọc corpus nguồn thật."""

import json
from unittest.mock import Mock

import pytest

from backend.core.config import ROOT, Settings
from backend.rag.vector_store import VectorStore
from ingestion.chunker import chunk_document
from ingestion.document_loader import load_document
from ingestion.index_documents import index_manifest


def test_index_manifest_is_repeatable_and_reports_bad_file(tmp_path):
    """Index lặp không tăng chunk trùng và vẫn báo riêng tài liệu bị thiếu."""
    source = tmp_path / "one.md"
    source.write_text("# Kiến thức\n\nĐoạn văn dành riêng cho kiểm thử phần mềm.", encoding="utf-8")
    manifest = tmp_path / "manifest.json"
    manifest.write_text(
        json.dumps(
            [
                {
                    "document_id": "one",
                    "path": "one.md",
                    "title": "Kiểm thử",
                    "source_url": "https://www.niddk.nih.gov/health-information/diabetes",
                },
                {
                    "document_id": "bad",
                    "path": "missing.md",
                    "title": "Lỗi",
                    "source_url": "https://www.niddk.nih.gov/health-information/diabetes",
                },
            ]
        ),
        encoding="utf-8",
    )
    embeddings = Mock()
    embeddings.embed.side_effect = lambda texts: [[1.0] + [0.0] * 767 for _ in texts]
    store = VectorStore(Settings(chroma_dir=tmp_path / "db"))
    report = index_manifest(manifest, embeddings, store)
    assert report["documents"] == 1 and report["chunks"] == 1
    assert report["errors"][0]["document_id"] == "bad"
    embeddings.embed.reset_mock()
    repeated = index_manifest(manifest, embeddings, store)
    assert repeated["documents"] == 0 and repeated["unchanged_documents"] == 1
    embeddings.embed.assert_not_called()
    assert store.collection.count() == 1


def test_incremental_index_only_updates_changed_document(tmp_path):
    """Chỉ tạo embedding cho nguồn đổi, loại chunk cũ và giữ nguồn khác nguyên vẹn."""
    entries = [
        {
            "document_id": name,
            "path": f"{name}.txt",
            "title": name,
            "source_url": "https://www.niddk.nih.gov/health-information/diabetes",
        }
        for name in ["one", "two"]
    ]
    for item in entries:
        (tmp_path / item["path"]).write_text("Original content.", encoding="utf-8")
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps(entries), encoding="utf-8")
    embeddings = Mock()
    embeddings.embed.side_effect = lambda texts: [[1.0] + [0.0] * 767 for _ in texts]
    store = VectorStore(Settings(chroma_dir=tmp_path / "db"))
    index_manifest(manifest, embeddings, store)
    old = store.collection.get(where={"document_id": "one"})["ids"]
    other = store.collection.get(where={"document_id": "two"}, include=["documents", "metadatas"])
    (tmp_path / "one.txt").write_text("# New\nChanged content.", encoding="utf-8")
    embeddings.embed.reset_mock()
    result = index_manifest(manifest, embeddings, store)
    assert result["documents"] == 1 and result["unchanged_documents"] == 1
    embeddings.embed.assert_called_once_with(["Changed content."])
    assert store.collection.get(ids=old)["ids"] == []
    assert store.collection.count() == 2
    assert (
        store.collection.get(where={"document_id": "two"}, include=["documents", "metadatas"])
        == other
    )
    embeddings.embed.reset_mock()
    assert index_manifest(manifest, embeddings, store)["unchanged_documents"] == 2
    embeddings.embed.assert_not_called()


def test_index_failure_preserves_existing_chunks(tmp_path):
    """Embedding thất bại không xóa hoặc thay một phần nội dung đang sử dụng."""
    source = tmp_path / "one.md"
    source.write_text("Original content.", encoding="utf-8")
    manifest = tmp_path / "manifest.json"
    manifest.write_text(
        json.dumps(
            [
                {
                    "document_id": "one",
                    "path": "one.md",
                    "title": "One",
                    "source_url": "https://www.niddk.nih.gov/health-information/diabetes",
                }
            ]
        ),
        encoding="utf-8",
    )
    store = VectorStore(Settings(chroma_dir=tmp_path / "db"))
    embeddings = Mock()
    embeddings.embed.return_value = [[1.0] + [0.0] * 767]
    index_manifest(manifest, embeddings, store)
    original = store.collection.get(include=["documents", "metadatas"])
    source.write_text("Changed content.", encoding="utf-8")
    from backend.core.errors import ServiceError

    embeddings.embed.side_effect = ServiceError("API unavailable", "embedding_unavailable")
    result = index_manifest(manifest, embeddings, store)
    assert result["documents"] == 0 and result["errors"]
    assert store.collection.get(include=["documents", "metadatas"]) == original


def test_check_only_selection_and_unsupported_file_isolation(tmp_path):
    """Kiểm tra không cần key/Chroma; DOC cũ báo riêng và TXT vẫn xử lý được."""
    (tmp_path / "ok.txt").write_text("Valid text.", encoding="utf-8")
    (tmp_path / "bad.doc").write_bytes(b"old document")
    manifest = tmp_path / "manifest.json"
    manifest.write_text(
        json.dumps(
            [
                {
                    "document_id": name,
                    "path": filename,
                    "title": name,
                    "source_url": "https://www.niddk.nih.gov/health-information/diabetes",
                }
                for name, filename in [("good", "ok.txt"), ("bad", "bad.doc")]
            ]
        ),
        encoding="utf-8",
    )
    result = index_manifest(manifest, check_only=True)
    assert result["documents"] == 1 and result["errors"][0]["document_id"] == "bad"
    assert "LibreOffice" in result["errors"][0]["error"]
    selected = index_manifest(manifest, check_only=True, document_ids={"good"})
    assert selected["documents"] == 1 and selected["errors"] == []
    with pytest.raises(ValueError, match="manifest"):
        index_manifest(manifest, check_only=True, document_ids={"missing"})


def test_real_sources_load_and_chunk():
    """Đọc từng nguồn thật và bảo đảm chunk giữ đúng URL xuất xứ."""
    manifest = ROOT / "data/knowledge/manifest.json"
    entries = json.loads(manifest.read_text(encoding="utf-8"))
    for item in entries:
        path = manifest.parent / item["path"]
        if not path.exists():
            pytest.skip("Chạy ingestion.download_sources trước kiểm thử nguồn thật.")
        chunks = chunk_document(
            load_document(path, item["document_id"], item["title"], item["source_url"])
        )
        assert chunks
        assert all(chunk.metadata["source_url"] == item["source_url"] for chunk in chunks)
