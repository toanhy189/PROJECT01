"""Chuyển tài liệu thành các đoạn có embedding để lưu vào ChromaDB."""

import argparse
import json
from pathlib import Path

from backend.core.config import ROOT, get_settings
from backend.core.errors import ServiceError
from backend.rag.embedding_service import EmbeddingService
from backend.rag.vector_store import VectorStore
from ingestion.chunker import chunk_document
from ingestion.document_loader import load_document


def index_manifest(
    manifest: Path,
    embeddings: EmbeddingService | None = None,
    store: VectorStore | None = None,
    *,
    document_ids: set[str] | None = None,
    check_only: bool = False,
) -> dict:
    """Kiểm tra hoặc cập nhật từng tài liệu thay đổi, giữ nguyên tài liệu còn lại."""
    if not check_only and (embeddings is None or store is None):
        raise ValueError("Cần dịch vụ embedding và kho vector để index thật.")
    entries = json.loads(manifest.read_text(encoding="utf-8"))
    if len({item["document_id"] for item in entries}) != len(entries):
        raise ValueError("Document ID trong manifest bị trùng.")
    if document_ids is not None:
        unknown = document_ids - {item["document_id"] for item in entries}
        if unknown:
            raise ValueError(f"Document ID không có trong manifest: {', '.join(sorted(unknown))}")
        entries = [item for item in entries if item["document_id"] in document_ids]
    report = {"documents": 0, "chunks": 0, "unchanged_documents": 0, "errors": [], "results": []}
    base = manifest.parent.resolve()
    for item in entries:
        try:
            path = (base / item["path"]).resolve()
            if not path.is_relative_to(base):
                raise ValueError("Đường dẫn tài liệu nằm ngoài thư mục manifest.")
            document = load_document(path, item["document_id"], item["title"], item["source_url"])
            chunks = chunk_document(document)
            if not chunks:
                raise ValueError("Tài liệu không tạo được chunk; không thay chỉ mục cũ.")
            result = {
                "document_id": document.document_id,
                "source_type": document.source_type,
                "chunks": len(chunks),
                "status": "checked" if check_only else "indexed",
            }
            if check_only:
                report["documents"] += 1
                report["chunks"] += len(chunks)
                report["results"].append(result)
                continue
            if store.document_matches(document.document_id, chunks):
                report["unchanged_documents"] += 1
                result["status"] = "unchanged"
                report["results"].append(result)
                continue
            vectors = []
            # Gửi theo lô nhỏ thay vì nhét toàn bộ tài liệu vào một yêu cầu embedding.
            for offset in range(0, len(chunks), 32):
                vectors.extend(
                    embeddings.embed([chunk.text for chunk in chunks[offset : offset + 32]])
                )
            # Chỉ cập nhật tài liệu khi đã nhận đủ vector; tránh thay bằng dữ liệu nửa chừng.
            store.replace_document(document.document_id, chunks, vectors)
            report["documents"] += 1
            report["chunks"] += len(chunks)
            report["results"].append(result)
        except (OSError, ValueError, KeyError, ServiceError) as exc:
            report["errors"].append({"document_id": item.get("document_id"), "error": str(exc)})
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Index PDF/DOCX/TXT/Markdown bằng Custom RAG")
    parser.add_argument("--manifest", type=Path, default=ROOT / "data/knowledge/manifest.json")
    parser.add_argument("--document-id", action="append", help="Chỉ xử lý ID này; có thể lặp lại")
    parser.add_argument(
        "--check-only",
        action="store_true",
        help="Chỉ kiểm tra loader/chunk, không gọi Gemini/Chroma",
    )
    args = parser.parse_args()
    settings = get_settings()
    # Kiểm tra khóa trước khi tạo thư mục chỉ mục.
    if not args.check_only and not settings.gemini_api_key:
        parser.exit(1, "Cần GEMINI_API_KEY trong .env để index tài liệu thật.\n")
    report = index_manifest(
        args.manifest,
        None if args.check_only else EmbeddingService(settings),
        None if args.check_only else VectorStore(settings),
        document_ids=set(args.document_id) if args.document_id else None,
        check_only=args.check_only,
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))
    raise SystemExit(1 if report["errors"] else 0)
