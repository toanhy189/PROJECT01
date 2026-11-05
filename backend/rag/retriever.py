"""Truy xuất chunk gần câu hỏi và loại bằng chứng thiếu metadata hoặc quá xa."""

import math
import threading
import time

from chromadb.errors import ChromaError

from backend.core.config import Settings
from backend.core.errors import ServiceError
from backend.rag.corpus import collection_rows, fingerprint, valid_row
from backend.rag.embedding_service import EmbeddingService
from backend.rag.fusion import guard_vector_candidates, reciprocal_rank_fusion
from backend.rag.models import Evidence, RetrievalResult
from backend.rag.snapshot import load_active_snapshot
from backend.rag.source_policy import source_allowed
from backend.rag.vector_store import VectorStore


class Retriever:
    """Kết nối query embedding với ChromaDB và lọc bằng chứng trước khi sinh trả lời."""

    def __init__(
        self,
        settings: Settings,
        embeddings: EmbeddingService | None = None,
        store: VectorStore | None = None,
    ) -> None:
        """Nhận dịch vụ embedding và kho vector tùy chọn để hỗ trợ test độc lập."""
        self.settings = settings
        self.embeddings = embeddings or EmbeddingService(settings)
        self.store = store
        self.reranker = None
        self.reranker_lock = threading.Lock()

    def retrieve(self, question: str, k: int | None = None) -> list[Evidence]:
        """Giữ giao diện cũ, trả tối đa k bằng chứng sau khi hợp nhất."""
        return self.retrieve_with_trace(question, k).documents

    def retrieve_with_trace(self, question: str, k: int | None = None) -> RetrievalResult:
        """Truy xuất vector/BM25/graph trên cùng snapshot và ghi trace riêng từng lần."""
        question = " ".join(question.split())
        if not question:
            return RetrievalResult([])
        limit = k if k is not None else self.settings.retrieval_k
        if not 1 <= limit <= 100:
            raise ValueError("Top-k phải trong khoảng 1–100.")
        trace = {
            "mode": "vector",
            "warnings": [],
            "graph": {"linked_entities": [], "paths": []},
            "channel_counts": {},
            "selected_chunk_ids": [],
            "reranker": "disabled",
        }
        enhanced = (
            self.settings.enable_graph_retrieval
            or self.settings.enable_hybrid_search
            or self.settings.enable_wiki
        )
        snapshot = None
        if enhanced:
            try:
                snapshot = load_active_snapshot(self.settings)
                trace.update(
                    snapshot_id=snapshot.snapshot_id, corpus_version=snapshot.corpus_version
                )
            except (OSError, ValueError, KeyError, ServiceError, ChromaError):
                trace["warnings"].append("snapshot_unavailable_using_vector")
        store = snapshot.store if snapshot else self.store or VectorStore(self.settings)
        candidate_limit = (
            max(limit, self.settings.retrieval_candidate_k)
            if snapshot or self.settings.enable_reranking
            else limit
        )
        rankings = []
        vector_error: ServiceError | None = None
        try:
            vector = self.embeddings.embed([question], query=True)[0]
            result = store.search(vector, candidate_limit)
            ranking = self._vector_candidates(result)
            rankings.append(ranking)
            trace["channel_counts"]["vector"] = len(ranking)
        except ServiceError as exc:
            if snapshot is None or not (
                self.settings.enable_graph_retrieval or self.settings.enable_hybrid_search
            ):
                raise
            trace["warnings"].append("vector_unavailable_using_local_indexes")
            vector_error = exc
        if snapshot and self.settings.enable_hybrid_search:
            ranking = snapshot.lexical.search(question, candidate_limit)
            rankings.append(ranking)
            trace["channel_counts"]["bm25"] = len(ranking)
        if snapshot and self.settings.enable_graph_retrieval:
            graph_started = time.perf_counter()
            try:
                ranking, graph_trace = snapshot.graph.search(
                    question,
                    candidate_limit,
                    self.settings.graph_max_hops,
                    self.settings.graph_max_paths,
                )
            except ServiceError as exc:
                ranking = []
                graph_trace = {
                    "backend": self.settings.graph_backend,
                    "status": "fallback",
                    "error_code": exc.code,
                    "connected": exc.code in {"neo4j_snapshot_mismatch", "neo4j_invalid_evidence"},
                    "linked_entities": [],
                    "paths": [],
                    "latency_ms": round((time.perf_counter() - graph_started) * 1000, 3),
                }
                trace["warnings"].append(f"{exc.code}_using_vector_bm25")
            trace["graph"] = graph_trace
            rankings.append(ranking)
            trace["channel_counts"]["graph"] = len(ranking)
        rankings = [
            [
                item
                for item in ranking
                if source_allowed(item.metadata, question, self.settings.enable_wiki)
            ]
            for ranking in rankings
        ]
        trace["wiki_policy"] = "background_only" if self.settings.enable_wiki else "disabled"
        if len(rankings) > 1:
            candidates = reciprocal_rank_fusion(rankings, self.settings.rrf_constant)
            if (
                self.settings.fusion_policy == "vector_guarded"
                and "vector" in trace["channel_counts"]
            ):
                candidates = guard_vector_candidates(candidates, rankings[0], limit)
            trace["mode"] = "hybrid_graph" if self.settings.enable_graph_retrieval else "hybrid"
        else:
            candidates = rankings[0] if rankings else []
            if candidates and "vector" not in trace["channel_counts"]:
                trace["mode"] = "graph" if "graph" in trace["channel_counts"] else "bm25"
        if self.settings.enable_reranking and candidates:
            from backend.rag.reranker import LocalReranker

            with self.reranker_lock:
                if self.reranker is None:
                    self.reranker = LocalReranker(self.settings)
            candidates, trace["reranker"] = self.reranker.rerank(question, candidates)
        # Không dùng candidate từ một collection đã bị thay đổi trong lúc truy xuất.
        if snapshot and fingerprint(collection_rows(store.collection)) != snapshot.corpus_version:
            fallback_settings = self.settings.model_copy(
                update={
                    "enable_graph_retrieval": False,
                    "enable_hybrid_search": False,
                    "enable_wiki": False,
                    "enable_reranking": False,
                }
            )
            fallback = Retriever(
                fallback_settings, self.embeddings, self.store
            ).retrieve_with_trace(question, limit)
            fallback.trace["warnings"].append("snapshot_changed_during_query")
            return fallback
        selected = candidates[:limit]
        if not selected and vector_error is not None:
            raise vector_error
        trace["fusion_policy"] = self.settings.fusion_policy
        trace["selected_chunk_ids"] = [item.metadata["chunk_id"] for item in selected]
        trace["candidates"] = [
            {
                "chunk_id": item.metadata["chunk_id"],
                "channels": item.channels,
                "distance": item.distance,
                "rank_score": item.score,
            }
            for item in candidates[: self.settings.retrieval_candidate_k]
        ]
        return RetrievalResult(selected, trace)

    def _vector_candidates(self, result: dict) -> list[Evidence]:
        """Lọc cosine chỉ trên nhánh vector, giữ nguyên ngưỡng baseline."""
        evidence = []
        rows = zip(
            result["ids"][0], result["documents"][0], result["metadatas"][0], result["distances"][0]
        )
        for chunk_id, text, metadata, distance in rows:
            if not valid_row({"chunk_id": chunk_id, "text": text, "metadata": metadata or {}}):
                continue
            # Khoảng cách cosine càng nhỏ càng gần; ngưỡng này chưa phải xác suất liên quan.
            if not math.isfinite(distance) or distance > self.settings.max_cosine_distance:
                continue
            evidence.append(Evidence(text, metadata, float(distance), channels=["vector"]))
        return evidence
