"""Kiểm tra backend hoạt động và response có request ID."""

from fastapi.testclient import TestClient

from backend.main import app


def test_health():
    """Xác nhận health trả HTTP 200 và middleware gắn mã yêu cầu."""
    response = TestClient(app).get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    assert response.headers["X-Request-ID"]
