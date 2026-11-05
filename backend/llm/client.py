"""Tạo kết nối Gemini với khóa backend, timeout và giới hạn retry."""

from google import genai
from google.genai import types

from backend.core.config import Settings
from backend.core.errors import ServiceError


def make_client(settings: Settings) -> genai.Client:
    """Từ chối khi chưa có key và tạo client có thời gian chờ hữu hạn."""
    if not settings.gemini_api_key:
        raise ServiceError("Chưa cấu hình GEMINI_API_KEY trong .env backend.", "gemini_key_missing")
    return genai.Client(
        api_key=settings.gemini_api_key,
        http_options=types.HttpOptions(
            timeout=settings.gemini_timeout_ms,
            retry_options=types.HttpRetryOptions(attempts=1),
        ),
    )
