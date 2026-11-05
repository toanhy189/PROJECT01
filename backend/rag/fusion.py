"""Hợp nhất theo thứ hạng và loại trùng bằng chunk ID chuẩn."""

from dataclasses import replace

from backend.rag.models import Evidence


def reciprocal_rank_fusion(rankings: list[list[Evidence]], constant: int = 60) -> list[Evidence]:
    """Cộng nghịch đảo thứ hạng từng nhánh; không cộng điểm khác thang đo."""
    if constant < 1:
        raise ValueError("Hằng số RRF phải dương.")
    merged: dict[str, Evidence] = {}
    for ranking in rankings:
        seen = set()
        for rank, candidate in enumerate(ranking, 1):
            cid = candidate.metadata["chunk_id"]
            if cid in seen:
                continue
            seen.add(cid)
            if cid not in merged:
                merged[cid] = replace(candidate, channels=[], graph_paths=[], score=0)
            current = merged[cid]
            if current.text != candidate.text or current.metadata != candidate.metadata:
                raise ValueError(
                    "Cùng chunk ID nhưng khác nội dung/metadata; không hợp nhất corpus lệch."
                )
            current.score += 1 / (constant + rank)
            current.channels = sorted(set(current.channels + candidate.channels))
            if candidate.distance is not None:
                current.distance = candidate.distance
            for path in candidate.graph_paths:
                if path not in current.graph_paths:
                    current.graph_paths.append(path)
    return sorted(
        merged.values(), key=lambda candidate: (-candidate.score, candidate.metadata["chunk_id"])
    )


def guard_vector_candidates(
    candidates: list[Evidence], vector: list[Evidence], limit: int
) -> list[Evidence]:
    """Giữ tập top-k vector, dùng RRF đổi thứ tự và bổ sung khi vector chưa đủ k."""
    anchors = {item.metadata["chunk_id"] for item in vector[:limit]}
    return [item for item in candidates if item.metadata["chunk_id"] in anchors] + [
        item for item in candidates if item.metadata["chunk_id"] not in anchors
    ]
