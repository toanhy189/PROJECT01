"""Các endpoint phân loại và hỏi đáp, dùng chung dịch vụ workflow."""

from typing import Annotated

from chromadb.errors import ChromaError
from fastapi import APIRouter, Depends, Request

from backend.agents.safety import unsafe_request
from backend.api.tools_routes import router as tools_router
from backend.core.errors import ServiceError
from backend.graph.workflow import Workflow, get_workflow
from backend.rag.context_builder import build_context
from backend.rag.retriever import Retriever
from backend.rag.snapshot import load_active_snapshot
from backend.schemas.api import (
    AnalysisResponse,
    AnalyzeRequest,
    ChatRequest,
    ModelInfo,
    PredictionResult,
    PredictRequest,
    RetrieveRequest,
)

router = APIRouter(prefix="/api/v1")
router.include_router(tools_router)
WorkflowDep = Annotated[Workflow, Depends(get_workflow)]


@router.get("/model-info", response_model=ModelInfo)
def model_info(workflow: WorkflowDep) -> ModelInfo:
    """Đọc trạng thái và metadata của model artifact đang có trên máy."""
    return workflow.predictor.info()


@router.post("/predict", response_model=PredictionResult)
def predict(payload: PredictRequest, workflow: WorkflowDep) -> PredictionResult:
    """Phân loại 21 đặc trưng đã được Pydantic kiểm tra, không gọi Gemini."""
    return workflow.predictor.predict(payload.patient_features)


@router.post("/chat", response_model=AnalysisResponse)
def chat(payload: ChatRequest, request: Request, workflow: WorkflowDep) -> AnalysisResponse:
    """Gửi câu hỏi độc lập qua workflow và giữ request ID của HTTP request."""
    return workflow.run(
        request.state.request_id, payload.user_query, payload.patient_features, payload.focus
    )


@router.post("/analyze", response_model=AnalysisResponse)
def analyze(payload: AnalyzeRequest, request: Request, workflow: WorkflowDep) -> AnalysisResponse:
    """Điều phối features, câu hỏi hoặc cả hai qua các nhánh LangGraph."""
    return workflow.run(
        request.state.request_id, payload.user_query, payload.patient_features, payload.focus
    )


@router.get("/retrieval-info")
def retrieval_info(workflow: WorkflowDep) -> dict:
    """Báo tính năng/snapshot hiện tại, không gọi Gemini hoặc trả API key."""
    retriever = workflow.retriever
    if not isinstance(retriever, Retriever):
        return {"status": "custom_retriever"}
    settings = retriever.settings
    report = {
        "graph_enabled": settings.enable_graph_retrieval,
        "graph_backend": settings.graph_backend,
        "hybrid_enabled": settings.enable_hybrid_search,
        "wiki_enabled": settings.enable_wiki,
        "reranker_enabled": settings.enable_reranking,
        "top_k": settings.retrieval_k,
    }
    try:
        snapshot = load_active_snapshot(settings)
        report.update(
            status="ready",
            snapshot_id=snapshot.snapshot_id,
            corpus_version=snapshot.corpus_version,
            chunks=len(snapshot.rows),
            entities=len(snapshot.graph.entities),
            relations=len(snapshot.graph.relations),
        )
    except (OSError, ValueError, KeyError, ChromaError, ServiceError):
        report["status"] = "snapshot_unavailable_vector_fallback"
    return report


@router.get("/graph/stats")
def graph_stats(workflow: WorkflowDep) -> dict:
    """Kiểm tra database thật, không lấy số node JSON rồi báo Neo4j đã sẵn sàng."""
    if not isinstance(workflow.retriever, Retriever):
        return {"status": "custom_retriever"}
    settings = workflow.retriever.settings
    if settings.graph_backend != "neo4j":
        return {"backend": settings.graph_backend, "status": "neo4j_not_selected"}
    from backend.rag.neo4j_connection import get_connection

    try:
        snapshot = load_active_snapshot(settings)
        connection = get_connection(settings)
        rows = connection.read(
            "MATCH (s:GraphSnapshot {snapshot_id:$sid}) "
            "OPTIONAL MATCH (n {snapshot_id:$sid}) WHERE n.uid IS NOT NULL "
            "RETURN s.status AS status, s.corpus_version AS corpus_version, "
            "s.graph_hash AS graph_hash, "
            "labels(n)[0] AS label, count(n) AS count",
            {"sid": snapshot.snapshot_id},
        )
        ready = bool(rows) and all(
            row["status"] == "ready"
            and row["corpus_version"] == snapshot.corpus_version
            and row["graph_hash"] == getattr(snapshot.graph, "graph_hash", None)
            for row in rows
        )
        return {
            "backend": "neo4j",
            "connected": True,
            "status": "ready" if ready else "snapshot_mismatch",
            "snapshot_id": snapshot.snapshot_id,
            "counts": {row["label"]: row["count"] for row in rows if row["label"]},
        }
    except (ServiceError, OSError, ValueError, KeyError, ChromaError) as exc:
        return {
            "backend": "neo4j",
            "status": "unavailable",
            "connected": False,
            "error_code": getattr(exc, "code", "snapshot_unavailable"),
        }


@router.post("/retrieve")
def retrieve_evidence(payload: RetrieveRequest, workflow: WorkflowDep) -> dict:
    """Xuất bằng chứng/đường đi để demo GraphRAG, không sinh câu trả lời bằng LLM."""
    if unsafe_request(payload.user_query):
        return {"documents": [], "trace": {"safety": "blocked"}}
    if not isinstance(workflow.retriever, Retriever):
        return {"documents": [], "trace": {"status": "custom_retriever"}}
    retriever = workflow.retriever
    if payload.retrieval_mode != "configured":
        settings = retriever.settings.model_copy(
            update={
                "enable_graph_retrieval": payload.retrieval_mode in {"graph", "hybrid_graph"},
                "enable_hybrid_search": payload.retrieval_mode == "hybrid_graph",
                "enable_reranking": False,
            }
        )
        retriever = Retriever(settings, retriever.embeddings, retriever.store)
    result = retriever.retrieve_with_trace(payload.user_query)
    _, citations = build_context(result.documents, retriever.settings.context_max_chars)
    used = {source.chunk_id for source in citations}
    result.trace["context_chunk_ids"] = sorted(used)
    for path in result.trace.get("graph", {}).get("paths", []):
        path["used_in_context"] = set(path["chunk_ids"]).issubset(used)
    return {
        "documents": [
            {
                "text": item.text,
                "metadata": item.metadata,
                "channels": item.channels,
                "distance": item.distance,
            }
            for item in result.documents
        ],
        "trace": result.trace,
    }
