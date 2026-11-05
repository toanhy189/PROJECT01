"""Tải các bài trong manifest và ghi báo cáo nguồn gốc để đối chiếu."""

import argparse
import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

import httpx

from backend.core.config import ROOT
from ingestion.document_loader import valid_source_url
from ingestion.html_parser import extract_article
from ingestion.text_cleaner import clean_text


def download_sources(manifest: Path, document_ids: set[str] | None = None) -> dict:
    """Tải phần nội dung NIDDK, bỏ hình, logo, điều hướng và ghi nguồn."""
    entries = json.loads(manifest.read_text(encoding="utf-8"))
    if document_ids is not None:
        unknown = document_ids - {entry["document_id"] for entry in entries}
        if unknown:
            raise ValueError("Document ID không có trong manifest.")
        entries = [entry for entry in entries if entry["document_id"] in document_ids]
    report = {"downloaded": [], "skipped": [], "errors": []}
    with httpx.Client(timeout=60, follow_redirects=True) as client:
        for entry in entries:
            try:
                if Path(entry["path"]).suffix.lower() != ".md":
                    # Tệp import thủ công không được ghi đè bằng HTML chuyển sang Markdown.
                    report["skipped"].append({"document_id": entry["document_id"]})
                    continue
                if not valid_source_url(entry["source_url"]):
                    raise ValueError("URL nguồn không hợp lệ.")
                response = client.get(entry["source_url"])
                response.raise_for_status()
                body = clean_text(extract_article(response.text))
                if len(body) < 500:
                    raise ValueError("Nội dung quá ngắn; không lưu trang lỗi.")
                path = (manifest.parent / entry["path"]).resolve()
                # Kiểm tra sau resolve để đường dẫn trong manifest không thoát thư mục nguồn.
                if not path.is_relative_to(manifest.parent.resolve()):
                    raise ValueError("Đường dẫn nằm ngoài thư mục nguồn.")
                content = f"# {entry['title']}\n\n{body}\n"
                changed = not path.exists() or path.read_text(encoding="utf-8") != content
                if changed:
                    path.write_text(content, encoding="utf-8")
                report["downloaded"].append(
                    # Checksum giúp nhận ra khi bản tài liệu local thay đổi sau lần tải này.
                    {
                        "document_id": entry["document_id"],
                        "source_url": entry["source_url"],
                        "retrieved_at": datetime.now(UTC).isoformat(),
                        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                        "characters": len(body),
                        "changed": changed,
                        "copyright_policy": "https://www.niddk.nih.gov/copyright",
                    }
                )
            except (httpx.HTTPError, OSError, ValueError) as exc:
                # Một nguồn lỗi không ngăn tải nguồn khác; báo cáo vẫn giữ ID để tra cứu.
                report["errors"].append(
                    {"document_id": entry["document_id"], "error_type": type(exc).__name__}
                )
    report_path = manifest.parent / "download_report.json"
    if document_ids is not None and report_path.exists():
        previous = json.loads(report_path.read_text(encoding="utf-8"))
        for key, items in report.items():
            retained = [
                item
                for item in previous.get(key, [])
                if item.get("document_id") not in document_ids
            ]
            report[key] = retained + items
    report_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Tải có chọn lọc tài liệu nguồn")
    parser.add_argument("--document-id", action="append")
    args = parser.parse_args()
    result = download_sources(
        ROOT / "data/knowledge/manifest.json",
        set(args.document_id) if args.document_id else None,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    raise SystemExit(1 if result["errors"] else 0)
