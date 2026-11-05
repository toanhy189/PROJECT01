"""API cho công cụ ML và dữ liệu có kiểm tra đầu vào, không gọi LLM."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException

from backend.graph.workflow import Workflow, get_workflow
from backend.ml.dataset_service import query_dataset
from backend.schemas.api import PredictRequest
from backend.schemas.tools import DatasetQuery, ScenarioRequest

router = APIRouter()
WorkflowDep = Annotated[Workflow, Depends(get_workflow)]


@router.post("/scenarios")
def scenario(payload: ScenarioRequest, workflow: WorkflowDep) -> dict:
    """Tính thật hai hồ sơ; trả 422 cho thay đổi sai mã hoặc sai miền."""
    try:
        return workflow.tools.scenario(payload.patient_features, payload.changes)
    except ValueError as exc:
        raise HTTPException(422, detail=str(exc)) from exc


@router.post("/models/compare")
def compare(payload: PredictRequest, workflow: WorkflowDep) -> dict:
    """Giữ kết quả model đã thành công khi model còn lại chưa sẵn sàng."""
    return workflow.tools.compare(payload.patient_features)


@router.get("/model-inspection")
def inspection(workflow: WorkflowDep) -> dict:
    """Đọc báo cáo ảnh hưởng và kiểm tra đúng phiên bản trọng số."""
    return workflow.tools.inspection()


@router.post("/dataset/query")
def dataset_query(payload: DatasetQuery, workflow: WorkflowDep) -> dict:
    """Thống kê nhãn thật trong khảo sát; không chạy dự đoán cá nhân."""
    try:
        return query_dataset(payload, workflow.settings.artifact_dir)
    except ValueError as exc:
        raise HTTPException(422, detail=str(exc)) from exc
