"""MediaWiki theo danh sách duyệt, revision cố định và chính sách request hữu hạn."""

import json
import re
import time
from collections.abc import Callable
from dataclasses import asdict
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from pathlib import Path
from urllib.parse import parse_qs, quote, urlparse

import httpx
from bs4 import BeautifulSoup

from backend.core.config import ROOT, get_settings
from backend.rag.corpus import atomic_json, fingerprint
from ingestion.document_loader import Document, valid_source_url
from ingestion.html_parser import extract_article
from ingestion.text_cleaner import clean_text


class WikiUnavailableError(ValueError):
    """Báo nguồn wiki bị chặn/lỗi; không thay bằng nội dung hoặc revision giả."""


def parse_wiki_html(html: str, title: str) -> str:
    """Làm sạch phần đã chọn của wiki, giữ bảng, heading và chú thích nội dung."""
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup.select(
        ".mw-editsection, .toc, .navbox, .vertical-navbox, .hatnote, .shortdescription, .noprint"
    ):
        tag.decompose()
    body = clean_text(extract_article(f"<article>{soup}</article>"))
    if len(body) < 100 or len(body) > 100000:
        raise ValueError("Nội dung wiki quá ngắn hoặc vượt giới hạn; không cắt ngầm.")
    return f"# {title}\n\n{body}"


class MediaWikiClient:
    """Chỉ gọi API Wikipedia en/vi, không crawl liên kết trong bài."""

    def __init__(
        self,
        client: httpx.Client,
        *,
        sleep: Callable[[float], None] = time.sleep,
        min_interval: float = 1.0,
    ) -> None:
        """Nhận HTTP client và bộ chờ để kiểm thử rate limit không cần mạng."""
        self.client, self.sleep, self.min_interval = client, sleep, min_interval
        self.last_request = 0.0

    def request(self, language: str, params: dict) -> dict:
        """Retry 429/maxlag hữu hạn, tôn trọng Retry-After và không vượt chặn 403."""
        if language not in {"en", "vi"}:
            raise ValueError("Chỉ duyệt wiki tiếng Việt/Anh.")
        for attempt in range(3):
            delay = self.min_interval - (time.monotonic() - self.last_request)
            if delay > 0:
                self.sleep(delay)
            self.last_request = time.monotonic()
            try:
                response = self.client.get(
                    f"https://{language}.wikipedia.org/w/api.php",
                    params={**params, "format": "json", "formatversion": 2, "maxlag": 5},
                )
                if response.status_code in {403, 401}:
                    raise WikiUnavailableError(
                        f"MediaWiki HTTP {response.status_code}: nguồn từ chối truy cập; không import."
                    )
                if response.status_code in {429, 503}:
                    raw = response.headers.get("Retry-After", str(2**attempt))
                    try:
                        wait = float(raw)
                    except ValueError:
                        wait = (parsedate_to_datetime(raw) - datetime.now(UTC)).total_seconds()
                    if wait > 60 or attempt == 2:
                        raise WikiUnavailableError(
                            "MediaWiki giới hạn truy cập; thử lại sau theo Retry-After."
                        )
                    self.sleep(max(wait, 0))
                    continue
                response.raise_for_status()
                data = response.json()
                if data.get("error", {}).get("code") == "maxlag" and attempt < 2:
                    self.sleep(2**attempt)
                    continue
                if "error" in data:
                    raise WikiUnavailableError("MediaWiki trả lỗi API; không thay bản nguồn cũ.")
                return data
            except (httpx.HTTPError, json.JSONDecodeError) as exc:
                raise WikiUnavailableError("Không lấy được JSON hợp lệ từ MediaWiki.") from exc
        raise WikiUnavailableError("MediaWiki không hoàn tất sau số lần thử hữu hạn.")

    def fetch(self, entry: dict) -> Document:
        """Khóa revision trước khi parse; chỉ lấy phần mở đầu đã khai báo trong scope."""
        if not entry.get("approved_for_ingestion") or entry.get("scope") != "lead":
            raise ValueError("Bài wiki/scope chưa được duyệt.")
        language = entry["language"]
        data = self.request(
            language,
            {
                "action": "query",
                "titles": entry["title"],
                "redirects": 1,
                "prop": "revisions",
                "rvprop": "ids|timestamp",
                "rvlimit": 1,
                "meta": "siteinfo",
                "siprop": "rightsinfo",
            },
        )
        pages = data["query"]["pages"]
        if len(pages) != 1 or pages[0].get("missing") or pages[0].get("ns") != 0:
            raise ValueError("Wiki không trả đúng một trang nội dung.")
        page = pages[0]
        revision = page["revisions"][0]
        revision_id = int(revision["revid"])
        rights = data["query"]["rightsinfo"]
        rights_url = rights.get("url", "")
        if not rights.get("text") or urlparse(rights_url).scheme != "https":
            raise ValueError("Chưa xác định được giấy phép wiki; không import.")
        parsed = self.request(
            language,
            {
                "action": "parse",
                "oldid": revision_id,
                "prop": "text|revid",
                "section": 0,
                "disableeditsection": 1,
            },
        )["parse"]
        if int(parsed["revid"]) != revision_id or int(parsed["pageid"]) != int(page["pageid"]):
            raise ValueError("Phiên bản nội dung wiki không khớp revision đã khóa.")
        html = parsed["text"]
        if isinstance(html, dict):
            html = html["*"]
        source_url = f"https://{language}.wikipedia.org/w/index.php?oldid={revision_id}"
        canonical_url = (
            f"https://{language}.wikipedia.org/wiki/{quote(page['title'].replace(' ', '_'))}"
        )
        content = parse_wiki_html(html, page["title"])
        return Document(
            entry["document_id"],
            page["title"],
            source_url,
            content,
            "html",
            {
                "source_provider": "wikipedia",
                "source_role": "background_only",
                "parser_format": "html",
                "language": language,
                "page_id": int(page["pageid"]),
                "revision_id": revision_id,
                "revision_timestamp": revision["timestamp"],
                "content_version": f"{page['pageid']}:{revision_id}",
                "section_scope": "lead",
                "retrieved_at": datetime.now(UTC).isoformat(),
                "license": rights["text"],
                "license_url": rights_url,
                "attribution_url": canonical_url,
                "changes": "Lead section only; HTML navigation removed; formatting normalized.",
                "sha256": fingerprint(content),
            },
        )


def download_wiki(manifest: Path, *, client: httpx.Client | None = None) -> dict:
    """Lưu tài liệu JSON trực tiếp; một lỗi nguồn không tạo dữ liệu thành công giả."""
    from contextlib import nullcontext

    settings = get_settings()
    report = {"downloaded": [], "errors": [], "scope": "lead_background_only"}
    entries = json.loads(manifest.read_text(encoding="utf-8"))
    with (
        nullcontext(client)
        if client
        else httpx.Client(
            timeout=30, follow_redirects=False, headers={"User-Agent": settings.wiki_user_agent}
        ) as http
    ):
        api = MediaWikiClient(http)
        for entry in entries:
            try:
                if not re.fullmatch(r"[a-z0-9-]+", entry["document_id"]):
                    raise ValueError("Document ID wiki không hợp lệ.")
                document = api.fetch(entry)
                path = manifest.parent / f"{document.document_id}.json"
                # Giữ timestamp/checksum bản cũ nếu nội dung và revision chưa đổi.
                old = json.loads(path.read_text(encoding="utf-8")) if path.exists() else None
                changed = (
                    old is None
                    or old["metadata"]["content_version"] != document.metadata["content_version"]
                    or old["metadata"]["sha256"] != document.metadata["sha256"]
                )
                if changed:
                    atomic_json(path, asdict(document))
                report["downloaded"].append(
                    {
                        "document_id": document.document_id,
                        "revision_id": document.metadata["revision_id"],
                        "changed": changed,
                    }
                )
            except (WikiUnavailableError, OSError, ValueError, KeyError) as exc:
                report["errors"].append(
                    {"document_id": entry.get("document_id"), "error": str(exc)}
                )
                if isinstance(exc, WikiUnavailableError) and "403" in str(exc):
                    # Không lặp gọi các bài khác khi cả nguồn đã từ chối vì robot policy.
                    break
    atomic_json(manifest.parent / "download_report.json", report)
    return report


def load_wiki_documents(manifest: Path) -> list[Document]:
    """Chỉ nạp JSON của bài trong manifest và kiểm tra revision/checksum trước index."""
    documents = []
    for entry in json.loads(manifest.read_text(encoding="utf-8")):
        if not entry.get("approved_for_ingestion"):
            continue
        if (
            not re.fullmatch(r"[a-z0-9-]+", entry["document_id"])
            or entry.get("language") not in {"vi", "en"}
            or entry.get("scope") != "lead"
        ):
            raise ValueError("Danh sách wiki chứa mục chưa được duyệt hoặc đường dẫn không hợp lệ.")
        path = manifest.parent / f"{entry['document_id']}.json"
        raw = json.loads(path.read_text(encoding="utf-8"))
        document = Document(**raw)
        metadata = document.metadata
        if (
            not valid_source_url(document.source_url)
            or document.document_id != entry["document_id"]
            or metadata.get("source_provider") != "wikipedia"
            or metadata.get("language") != entry["language"]
            or metadata.get("section_scope") != entry["scope"]
            or not metadata.get("license")
            or metadata.get("sha256") != fingerprint(document.text)
            or parse_qs(urlparse(document.source_url).query).get("oldid")
            != [str(metadata.get("revision_id"))]
        ):
            raise ValueError("Metadata wiki không hợp lệ hoặc không khớp bản đã tải.")
        documents.append(document)
    return documents


if __name__ == "__main__":
    result = download_wiki(ROOT / "data/wiki/manifest.json")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    raise SystemExit(1 if result["errors"] else 0)
