"""Kiểm thử tải HTML bằng HTTP giả lập, không gọi nguồn hoặc Gemini thật."""

import json
from pathlib import Path
from unittest.mock import MagicMock

import httpx
import pytest

from ingestion.download_sources import download_sources


def test_download_preserves_references_and_does_not_rewrite_unchanged_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Tải lặp giữ nguyên file sạch, ghi checksum và trạng thái thay đổi thật."""
    manifest = tmp_path / "manifest.json"
    manifest.write_text(
        json.dumps(
            [
                {
                    "document_id": "test",
                    "title": "Tài liệu thử",
                    "path": "test.md",
                    "source_url": "https://www.niddk.nih.gov/health-information/diabetes",
                }
            ]
        ),
        encoding="utf-8",
    )
    html = "<article><h2>Parent</h2><h3>Child</h3><p>" + "Test content. " * 50
    html += "</p><h2>References</h2><aside><p>[1] Reference text.</p></aside></article>"
    client_class = httpx.Client
    transport = httpx.MockTransport(lambda request: httpx.Response(200, text=html))
    monkeypatch.setattr(
        "ingestion.download_sources.httpx.Client",
        lambda **kwargs: client_class(transport=transport),
    )
    first = download_sources(manifest)
    path = tmp_path / "test.md"
    original_time = path.stat().st_mtime_ns
    original = path.read_text(encoding="utf-8")
    second = download_sources(manifest)
    assert first["errors"] == second["errors"] == []
    assert first["downloaded"][0]["changed"] is True
    assert second["downloaded"][0]["changed"] is False
    assert first["downloaded"][0]["sha256"] == second["downloaded"][0]["sha256"]
    assert path.stat().st_mtime_ns == original_time
    assert "### Child" in original and "[1] Reference text." in original


def test_bad_source_does_not_overwrite_existing_document(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Trang lỗi hoặc thiếu selector không được ghi đè bản nguồn đang hoạt động."""
    source = tmp_path / "test.md"
    source.write_text("Existing document.", encoding="utf-8")
    manifest = tmp_path / "manifest.json"
    manifest.write_text(
        json.dumps(
            [
                {
                    "document_id": "test",
                    "title": "Test",
                    "path": "test.md",
                    "source_url": "https://www.niddk.nih.gov/health-information/diabetes",
                }
            ]
        ),
        encoding="utf-8",
    )
    client_class = httpx.Client
    transport = httpx.MockTransport(lambda request: httpx.Response(200, text="<p>Error</p>"))
    monkeypatch.setattr(
        "ingestion.download_sources.httpx.Client",
        lambda **kwargs: client_class(transport=transport),
    )
    report = download_sources(manifest)
    assert len(report["errors"]) == 1 and report["downloaded"] == []
    assert source.read_text(encoding="utf-8") == "Existing document."


def test_web_downloader_does_not_overwrite_imported_files(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Tệp DOCX/PDF/TXT thêm vào manifest phải được giữ nguyên khi tải bài web."""
    entries = []
    for extension in ["docx", "pdf", "txt"]:
        (tmp_path / f"sample.{extension}").write_bytes(b"original bytes")
        entries.append({"document_id": extension, "path": f"sample.{extension}"})
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps(entries), encoding="utf-8")
    client = MagicMock()
    monkeypatch.setattr("ingestion.download_sources.httpx.Client", client)
    report = download_sources(manifest)
    assert len(report["skipped"]) == 3 and report["errors"] == []
    client.return_value.__enter__.return_value.get.assert_not_called()
    for extension in ["docx", "pdf", "txt"]:
        assert (tmp_path / f"sample.{extension}").read_bytes() == b"original bytes"


def test_selected_download_preserves_previous_report(tmp_path, monkeypatch):
    """Tải một nguồn mới không tải lại hoặc xóa báo cáo nguồn còn lại."""
    manifest = tmp_path / "manifest.json"
    entries = [{"document_id": name, "title": name, "path": f"{name}.md",
                "source_url": f"https://www.niddk.nih.gov/{name}"} for name in ("old", "new")]
    manifest.write_text(json.dumps(entries), encoding="utf-8")
    previous = {"downloaded": [{"document_id": "old", "sha256": "original"}], "errors": [], "skipped": []}
    (tmp_path / "download_report.json").write_text(json.dumps(previous), encoding="utf-8")
    requests = []
    def handle(request):
        requests.append(str(request.url))
        return httpx.Response(200, text="<article><p>" + "Source content. " * 50 + "</p></article>")
    client_class = httpx.Client
    monkeypatch.setattr("ingestion.download_sources.httpx.Client", lambda **kwargs: client_class(transport=httpx.MockTransport(handle)))
    report = download_sources(manifest, {"new"})
    assert requests == [entries[1]["source_url"]]
    assert report["downloaded"][0] == previous["downloaded"][0]
    assert report["downloaded"][1]["document_id"] == "new"
