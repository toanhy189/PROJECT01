"""Khởi tạo FastAPI, gắn API và xử lý log, lỗi mà không ghi dữ liệu đầu vào."""

import logging
import time
from collections.abc import Awaitable, Callable
from contextlib import asynccontextmanager
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.responses import Response

from backend.api.routes import router
from backend.core.config import get_settings
from backend.core.errors import ServiceError

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")
logger = logging.getLogger("diabetes.api")


@asynccontextmanager
async def lifespan(application: FastAPI):
    """Giữ khởi động độc lập Neo4j và đóng driver khi backend dừng."""
    from backend.rag.neo4j_connection import close_connections

    try:
        yield
    finally:
        close_connections()


def create_app() -> FastAPI:
    """Tạo ứng dụng với CORS local, request ID và bộ xử lý lỗi dùng chung."""
    application = FastAPI(title="Diabetes Multi-Agent", version="1.0.0", lifespan=lifespan)
    application.include_router(router)
    application.add_middleware(
        CORSMiddleware,
        allow_origins=get_settings().cors_origins,
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type"],
    )

    @application.middleware("http")
    async def track_request(
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        """Gắn ID và đo thời gian yêu cầu; chỉ log thông tin vận hành."""
        request.state.request_id = str(uuid4())
        start = time.perf_counter()
        response = await call_next(request)
        response.headers["X-Request-ID"] = request.state.request_id
        logger.info(
            "request_id=%s method=%s status=%s latency_ms=%.2f",
            request.state.request_id,
            request.method,
            response.status_code,
            (time.perf_counter() - start) * 1000,
        )
        return response

    @application.exception_handler(RequestValidationError)
    async def invalid_input(request: Request, exc: RequestValidationError) -> JSONResponse:
        """Trả tên trường sai thay vì phản chiếu dữ liệu sức khỏe đã nhập."""
        return JSONResponse(
            status_code=422,
            content={
                "detail": "Dữ liệu không hợp lệ. Kiểm tra đủ trường và mã giá trị.",
                "fields": [".".join(map(str, item["loc"])) for item in exc.errors()],
                "request_id": request.state.request_id,
            },
        )

    @application.exception_handler(ServiceError)
    async def service_error(request: Request, exc: ServiceError) -> JSONResponse:
        """Trả lỗi dịch vụ đã chuẩn hóa với HTTP 503 và mã theo dõi."""
        logger.warning("request_id=%s error_code=%s", request.state.request_id, exc.code)
        return JSONResponse(
            status_code=503,
            content={
                "detail": str(exc),
                "code": exc.code,
                "request_id": request.state.request_id,
            },
        )

    @application.exception_handler(Exception)
    async def unexpected_error(request: Request, exc: Exception) -> JSONResponse:
        """Ẩn chi tiết lỗi nội bộ và chỉ log loại lỗi cùng request ID."""
        # Không ghi exception text vì nhà cung cấp có thể chứa nội dung sức khỏe.
        logger.error("request_id=%s error_type=%s", request.state.request_id, type(exc).__name__)
        return JSONResponse(
            status_code=500,
            content={
                "detail": "Có lỗi xử lý nội bộ. Vui lòng thử lại.",
                "request_id": request.state.request_id,
            },
        )

    @application.get("/health")
    def health() -> dict[str, str]:
        """Báo backend hoạt động; không xác nhận model hoặc Gemini đã sẵn sàng."""
        return {"status": "ok", "service": "diabetes-multiagent"}

    return application


app = create_app()
