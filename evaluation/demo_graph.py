"""Xuất đường truy xuất GraphRAG từ câu hỏi đã cache, không giả lập câu trả lời LLM."""

import argparse
import json
from pathlib import Path

from backend.agents.nodes import Agents
from backend.core.config import ROOT, get_settings
from backend.rag.corpus import atomic_json
from backend.rag.retriever import Retriever
from evaluation.evaluate_retrieval import CachedQueries


def graph_demo(case_id: str) -> dict:
    """Dùng query embedding Gemini thật đã lưu để xem entity, cạnh và context nguồn."""
    settings = get_settings().model_copy(
        update={
            "enable_graph_retrieval": True,
            "enable_hybrid_search": False,
            "enable_wiki": False,
            "enable_reranking": False,
        }
    )
    gold = json.loads((ROOT / "evaluation/retrieval_gold.json").read_text(encoding="utf-8"))
    case = next(item for item in gold["cases"] if item["case_id"] == case_id)
    cache = CachedQueries(settings, ROOT / "artifacts/query_embeddings.json")
    retriever = Retriever(settings, cache)
    state = Agents(settings, None, retriever, None).knowledge({"user_query": case["question"]})
    trace = state["retrieval_trace"]
    trace["graph"]["paths"] = [path for path in trace["graph"]["paths"] if path["used_in_context"]][
        :5
    ]
    return {
        "demo_type": "retrieval_and_context_only_no_llm_generation",
        "case_id": case_id,
        "question": case["question"],
        "query_embedding": "real_gemini_cached",
        "retrieval_trace": trace,
        "citations": [source.model_dump() for source in state["citations"]],
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Demo graph có provenance, không gọi API lại")
    parser.add_argument("--case-id", default="r36")
    parser.add_argument("--output", type=Path, default=ROOT / "artifacts/graph_demo.json")
    args = parser.parse_args()
    result = graph_demo(args.case_id)
    atomic_json(args.output, result)
    print(
        json.dumps(
            {
                "case_id": args.case_id,
                "backend": result["retrieval_trace"]["graph"].get("backend"),
                "connected": result["retrieval_trace"]["graph"].get("connected"),
                "graph_latency_ms": result["retrieval_trace"]["graph"].get("latency_ms"),
                "linked_entities": result["retrieval_trace"]["graph"]["linked_entities"],
                "paths_in_context": len(result["retrieval_trace"]["graph"]["paths"]),
                "chunks_in_context": result["retrieval_trace"]["context_chunk_ids"],
            },
            ensure_ascii=True,
            indent=2,
        )
    )
