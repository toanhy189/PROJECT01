"""Xếp hạng đường truy xuất dùng chung, độc lập với nơi lưu Knowledge Graph."""

from backend.rag.corpus import row_evidence
from backend.rag.models import Evidence


def make_path(
    nodes: list[str],
    relations: list[dict],
    evidence: list[dict],
    starts: set[str],
    intents: set[str],
) -> dict:
    """Giữ nguyên hướng và điều kiện của từng phát biểu, không suy diễn bắc cầu."""
    return {
        "entities": nodes,
        "relations": relations,
        "evidence": evidence,
        "chunk_ids": sorted({item["chunk_id"] for item in evidence}),
        "hops": len(relations),
        "matched_query_entities": len(starts & set(nodes)),
        "intent_matches": sum(item["predicate"] in intents for item in relations),
        "source_quality": sum(
            (2 if item["source_provider"] != "wikipedia" else 0)
            + (1 if item["status"] == "human_reviewed" else 0)
            for item in evidence
        )
        / len(evidence),
        "inference": "navigation_only_no_transitive_claim",
    }


def rank_paths(
    paths: list[dict], rows: dict[str, dict], limit: int, max_paths: int, trace: dict
) -> tuple[list[Evidence], dict]:
    """Chuẩn hóa thứ tự và khử đường trùng trước khi chuyển sang RRF."""
    paths.sort(
        key=lambda p: (
            -p["matched_query_entities"],
            -p["intent_matches"],
            p["hops"],
            -p["source_quality"],
            p["entities"],
            [r["relation_id"] for r in p["relations"]],
        )
    )
    chosen, unique_paths, signatures = {}, [], set()
    for path in paths:
        signature = tuple(sorted(r["relation_id"] for r in path["relations"]))
        if signature in signatures:
            continue
        signatures.add(signature)
        if len(unique_paths) >= max_paths:
            break
        unique_paths.append(path)
        for cid in path["chunk_ids"]:
            if cid not in chosen:
                chosen[cid] = row_evidence(rows[cid], "graph")
                chosen[cid].score = float(len(paths) - len(unique_paths) + 1)
            chosen[cid].graph_paths.append(path)
    return list(chosen.values())[:limit], {
        **trace,
        "paths": unique_paths,
        "ranking_policy": "entity_coverage,intent_match,hops,source_quality,stable_ids",
    }
