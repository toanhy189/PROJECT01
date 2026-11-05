"""Schema request, response và giới hạn diễn giải kết quả của hệ thống."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from backend.schemas.features import PatientFeatures

LIMITATIONS = (
    "Mô hình học từ khảo sát BRFSS 2015 tại Hoa Kỳ. Lớp 1 gộp tiền tiểu đường "
    "và tiểu đường theo nhãn dữ liệu. Điểm mô hình không phải xác suất chẩn đoán "
    "hoặc nguy cơ mắc bệnh trong tương lai. Không thay thế xét nghiệm hay bác sĩ."
)


class StrictModel(BaseModel):
    """Schema đầu vào dùng chung, từ chối các trường ngoài đặc tả."""

    model_config = ConfigDict(extra="forbid")


class PredictRequest(StrictModel):
    """Yêu cầu phân loại chứa đầy đủ bộ đặc trưng đã được kiểm tra."""

    patient_features: PatientFeatures


class ChatRequest(StrictModel):
    """Câu hỏi độc lập, giới hạn độ dài và không chấp nhận nội dung rỗng."""

    user_query: str = Field(min_length=1, max_length=2000)
    patient_features: PatientFeatures | None = None
    focus: Literal["BMI"] | None = None

    @field_validator("user_query")
    @classmethod
    def clean_query(cls, value: str) -> str:
        """Bỏ khoảng trắng hai đầu và từ chối câu hỏi chỉ có khoảng trắng."""
        if not value.strip():
            raise ValueError("Vui lòng nhập câu hỏi.")
        return value.strip()


class AnalyzeRequest(StrictModel):
    """Cho phép gửi features, câu hỏi hoặc kết hợp cả hai."""

    patient_features: PatientFeatures | None = None
    user_query: str = Field(default="", max_length=2000)
    focus: Literal["BMI"] | None = None

    @model_validator(mode="after")
    def require_input(self) -> "AnalyzeRequest":
        """Từ chối yêu cầu không có câu hỏi lẫn bộ đặc trưng."""
        self.user_query = self.user_query.strip()
        if self.patient_features is None and not self.user_query:
            raise ValueError("Cần câu hỏi hoặc đầy đủ 21 đặc trưng.")
        return self


class RetrieveRequest(ChatRequest):
    """Chọn chế độ demo retrieval mà không đổi cấu hình chat mặc định."""

    retrieval_mode: Literal["configured", "vector", "graph", "hybrid_graph"] = "configured"


class PredictionResult(BaseModel):
    """Điểm, lớp, ngưỡng và phiên bản model kèm giới hạn diễn giải."""

    model_score: float = Field(ge=0, le=1)
    predicted_class: Literal[0, 1]
    threshold: float = Field(ge=0, le=1)
    model_version: str
    limitations: str = LIMITATIONS


class Citation(BaseModel):
    """Nguồn bằng chứng có ID, URL và nội dung chunk để người dùng đối chiếu."""

    citation_id: str
    document_id: str
    chunk_id: str
    title: str
    section: str
    source_url: str
    quote: str
    source_provider: str | None = None
    revision_id: int | None = None
    license: str | None = None
    license_url: str | None = None
    attribution_url: str | None = None
    section_scope: str | None = None
    changes: str | None = None


class TraceEntry(BaseModel):
    """Trạng thái và thời gian đo được của một node thực sự đã chạy."""

    agent: str
    status: Literal["ok", "error", "fallback"]
    latency_ms: float


class AnalysisResponse(BaseModel):
    """Kết quả workflow đã kiểm tra schema, gồm câu trả lời, nguồn, trace và lỗi."""

    request_id: str
    intent: Literal["prediction", "knowledge", "combined"]
    prediction_result: PredictionResult | None = None
    generated_answer: str
    citations: list[Citation]
    safety_status: Literal["passed", "fallback"]
    agent_trace: list[TraceEntry]
    errors: list[str]
    retrieval_trace: dict = Field(default_factory=dict)
    measurement_result: dict | None = None
    scenario_result: dict | None = None
    profile_hash: str | None = None


class ModelInfo(BaseModel):
    """Trạng thái model cùng thứ tự features, ngưỡng và giới hạn sử dụng."""

    ready: bool
    model_version: str | None = None
    feature_names: list[str]
    threshold: float | None = None
    limitations: str = LIMITATIONS
