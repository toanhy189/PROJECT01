"""BM25 và ánh xạ thuật ngữ có kiểm soát, không gọi LLM cho từng truy vấn."""

import re
import unicodedata

from rank_bm25 import BM25Okapi

from backend.rag.corpus import row_evidence
from backend.rag.models import Evidence

STOP_WORDS = {
    "la",
    "gi",
    "the",
    "nao",
    "co",
    "nhung",
    "va",
    "cua",
    "trong",
    "voi",
    "de",
    "duoc",
    "mot",
    "cac",
    "cho",
    "toi",
    "minh",
    "ban",
    "what",
    "is",
    "are",
    "a",
    "an",
    "of",
    "to",
    "in",
    "and",
    "does",
    "do",
    "how",
    "which",
    "can",
    "for",
    "about",
}


def normalize_term(text: str) -> str:
    """Chuẩn hóa dấu để ghép bí danh Việt–Anh, vẫn giữ nguyên văn bản nguồn."""
    text = unicodedata.normalize("NFD", text.casefold()).replace("đ", "d")
    return " ".join(re.findall(r"\w+", "".join(c for c in text if unicodedata.category(c) != "Mn")))


def tokenize(text: str) -> list[str]:
    """Giữ từ và chữ số cho BM25, bỏ một số từ chức năng phổ biến."""
    return [word for word in normalize_term(text).split() if word not in STOP_WORDS]


def link_entities(question: str, entities: list[dict]) -> list[dict]:
    """Ghép bí danh dài trước; thực thể chung không che tên típ bệnh cụ thể."""
    query = normalize_term(question)
    matches = []
    for entity in entities:
        for alias in {entity["name"], *entity.get("aliases", [])}:
            value = normalize_term(alias)
            if not value:
                continue
            for match in re.finditer(r"(?<!\w)" + re.escape(value) + r"(?!\w)", query):
                matches.append((match.start(), match.end(), entity["entity_id"], alias))
    matches.sort(key=lambda match: (-(match[1] - match[0]), match[0], match[2]))
    selected, occupied, seen = [], [], set()
    for start, end, eid, alias in matches:
        if eid in seen or any(start < right and end > left for left, right in occupied):
            continue
        occupied.append((start, end))
        seen.add(eid)
        selected.append({"entity_id": eid, "matched_alias": alias, "method": "controlled_alias"})
    return selected


def expand_query(question: str, entities: list[dict]) -> list[str]:
    """Giữ truy vấn gốc và thêm tên chuẩn của thực thể được nhận diện."""
    linked = {item["entity_id"] for item in link_entities(question, entities)}
    return list(
        dict.fromkeys(
            tokenize(question)
            + [
                token
                for entity in entities
                if entity["entity_id"] in linked
                for token in tokenize(entity["name"])
            ]
        )
    )


class LexicalIndex:
    """Xây BM25 trên đúng chunk của một snapshot corpus."""

    def __init__(self, rows: list[dict], entities: list[dict]) -> None:
        """Lưu corpus bất biến và tạo thống kê BM25 trong bộ nhớ."""
        self.rows, self.entities = rows, entities
        self.model = (
            BM25Okapi([tokenize(row["text"]) or ["_empty_"] for row in rows]) if rows else None
        )

    def search(self, question: str, limit: int) -> list[Evidence]:
        """Trả danh sách đã xếp hạng, không gán điểm BM25 thành cosine distance."""
        if self.model is None:
            return []
        scores = self.model.get_scores(expand_query(question, self.entities))
        ranked = sorted(
            zip(self.rows, scores), key=lambda item: (-float(item[1]), item[0]["chunk_id"])
        )
        result = []
        for row, score in ranked[:limit]:
            if score > 0:
                candidate = row_evidence(row, "bm25")
                candidate.score = float(score)
                result.append(candidate)
        return result
