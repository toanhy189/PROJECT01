"""Kiểm thử wiki bằng HTTP giả lập, không coi dữ liệu mock là bản tải thật."""

import json
from pathlib import Path

import httpx
import pytest

from ingestion.document_loader import valid_source_url
from ingestion.wiki_sources import (
    MediaWikiClient,
    WikiUnavailableError,
    download_wiki,
    load_wiki_documents,
    parse_wiki_html,
)

ENTRY = {
    "document_id": "wiki-test",
    "title": "Software sample",
    "language": "en",
    "approved_for_ingestion": True,
    "scope": "lead",
}
HTML = (
    "<div><span class='mw-editsection'>edit</span><p>"
    + "Software definition for parser verification. " * 5
    + "</p><h2>Nested heading</h2><table><tr><th>Label</th><th>Value</th></tr><tr><td>Example</td><td>123</td></tr></table></div>"
)


def wiki_reply(request: httpx.Request) -> httpx.Response:
    """Tạo hai đáp ứng API đã khóa revision dành riêng cho kiểm thử."""
    if request.url.params["action"] == "query":
        return httpx.Response(
            200,
            json={
                "query": {
                    "pages": [
                        {
                            "pageid": 7,
                            "ns": 0,
                            "title": "Software sample",
                            "revisions": [{"revid": 42, "timestamp": "2026-01-01T00:00:00Z"}],
                        }
                    ],
                    "rightsinfo": {
                        "text": "Test license",
                        "url": "https://creativecommons.org/licenses/by-sa/4.0/",
                    },
                }
            },
        )
    assert request.url.params["oldid"] == "42"
    assert request.url.params["section"] == "0"
    return httpx.Response(200, json={"parse": {"pageid": 7, "revid": 42, "text": HTML}})


def test_wiki_pins_revision_and_preserves_table():
    """Document giữ format parser riêng provider, revision, giấy phép và bảng."""
    with httpx.Client(transport=httpx.MockTransport(wiki_reply)) as client:
        document = MediaWikiClient(client, min_interval=0).fetch(ENTRY)
    assert document.source_type == "html" and document.metadata["source_provider"] == "wikipedia"
    assert document.source_url == "https://en.wikipedia.org/w/index.php?oldid=42"
    assert document.metadata["content_version"] == "7:42"
    assert document.metadata["license"] == "Test license"
    assert "| Example | 123 |" in document.text and "## Nested heading" in document.text
    assert "edit" not in document.text and document.metadata["section_scope"] == "lead"


def test_wiki_rate_limit_respects_retry_after():
    """HTTP 429 được chờ đúng số giây, không gọi dồn hoặc thử vô hạn."""
    attempts, waits = [], []

    def handler(request):
        """Giả lập một lần giới hạn trước đáp ứng hợp lệ."""
        attempts.append(request)
        return (
            httpx.Response(429, headers={"Retry-After": "7"})
            if len(attempts) == 1
            else wiki_reply(request)
        )

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        MediaWikiClient(client, min_interval=0, sleep=waits.append).fetch(ENTRY)
    assert waits == [7] and len(attempts) == 3


def test_wiki_403_stops_without_bypassing_policy():
    """Nguồn từ chối robot thì dừng, không đổi endpoint hoặc tạo dữ liệu giả."""
    attempts = []

    def handler(request):
        """Ghi số request khi nguồn trả chặn truy cập."""
        attempts.append(request)
        return httpx.Response(403, text="Robot policy")

    with (
        httpx.Client(transport=httpx.MockTransport(handler)) as client,
        pytest.raises(WikiUnavailableError, match="403"),
    ):
        MediaWikiClient(client, min_interval=0).fetch(ENTRY)
    assert len(attempts) == 1


def test_wiki_cannot_parse_different_revision():
    """API trả nhầm revision phải bị chặn trước lưu file/index."""

    def handler(request):
        """Chỉ đổi revision của phần parse để kiểm tra đối chiếu."""
        response = wiki_reply(request)
        data = response.json()
        if "parse" in data:
            data["parse"]["revid"] = 43
        return httpx.Response(200, json=data)

    with (
        httpx.Client(transport=httpx.MockTransport(handler)) as client,
        pytest.raises(ValueError, match="revision"),
    ):
        MediaWikiClient(client, min_interval=0).fetch(ENTRY)


@pytest.mark.parametrize(
    "url",
    [
        "https://en.wikipedia.org/wiki/Diabetes",
        "https://evil.wikipedia.org/w/index.php?oldid=42",
        "https://en.wikipedia.org/w/index.php?oldid=0",
        "https://en.wikipedia.org/w/index.php?oldid=42&oldid=43",
        "https://en.wikipedia.org/w/index.php?oldid=42&redirect=external",
    ],
)
def test_wiki_source_url_requires_approved_host_and_exact_revision(url):
    """Không mở rộng allowlist thành mọi wiki hoặc URL phiên bản nhập nhằng."""
    assert not valid_source_url(url)
    assert valid_source_url("https://vi.wikipedia.org/w/index.php?oldid=42")


def test_wiki_unknown_language_or_unapproved_page_is_rejected():
    """Manifest chưa duyệt không được tạo request ra mạng."""
    with httpx.Client(
        transport=httpx.MockTransport(lambda r: pytest.fail("unexpected request"))
    ) as client:
        api = MediaWikiClient(client, min_interval=0)
        with pytest.raises(ValueError):
            api.fetch({**ENTRY, "approved_for_ingestion": False})
        with pytest.raises(ValueError):
            api.fetch({**ENTRY, "language": "unknown"})


def test_wiki_download_repeat_and_checksum_validation(tmp_path: Path, monkeypatch):
    """Cùng revision không ghi lại document; metadata sai bị từ chối khi nạp."""
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps([ENTRY]), encoding="utf-8")
    original = MediaWikiClient
    monkeypatch.setattr(
        "ingestion.wiki_sources.MediaWikiClient", lambda client: original(client, min_interval=0)
    )
    with httpx.Client(transport=httpx.MockTransport(wiki_reply)) as client:
        first = download_wiki(manifest, client=client)
        path = tmp_path / "wiki-test.json"
        before = path.stat().st_mtime_ns
        second = download_wiki(manifest, client=client)
    assert first["downloaded"][0]["changed"] is True
    assert second["downloaded"][0]["changed"] is False
    assert path.stat().st_mtime_ns == before
    assert len(load_wiki_documents(manifest)) == 1
    raw = json.loads(path.read_text(encoding="utf-8"))
    raw["metadata"]["revision_id"] = 43
    path.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(ValueError, match="Metadata"):
        load_wiki_documents(manifest)


def test_wiki_parser_rejects_empty_content():
    """Không coi trang lỗi/ngắn là tài liệu wiki đã import thành công."""
    with pytest.raises(ValueError, match="ngắn"):
        parse_wiki_html("<p>Error</p>", "Error")
