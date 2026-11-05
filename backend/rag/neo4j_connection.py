"""Quản lý driver dùng chung, transaction giới hạn thời gian và lỗi an toàn."""

import threading
from collections.abc import Callable
from typing import Any

from neo4j import GraphDatabase, unit_of_work
from neo4j.exceptions import AuthError, DriverError, Neo4jError

from backend.core.config import Settings
from backend.core.errors import ServiceError
from backend.rag.corpus import fingerprint


class Neo4jConnection:
    """Một pool cho mỗi cấu hình kết nối trong process; session không dùng chung."""

    def __init__(self, settings: Settings) -> None:
        """Khởi tạo lazy để database lỗi không làm dừng Prediction hoặc Vector RAG."""
        if not settings.neo4j_password:
            raise ServiceError("Chưa cấu hình mật khẩu Neo4j.", "neo4j_not_configured")
        self.settings = settings
        self.driver = GraphDatabase.driver(
            settings.neo4j_uri,
            auth=(settings.neo4j_user, settings.neo4j_password),
            connection_timeout=settings.neo4j_connection_timeout_seconds,
            connection_acquisition_timeout=settings.neo4j_connection_timeout_seconds,
            max_connection_pool_size=settings.neo4j_pool_size,
            max_transaction_retry_time=0,
        )

    def query(self, text: str) -> str:
        """Managed transaction nhận Cypher string; timeout gắn vào unit_of_work."""
        return text

    def transaction(self, action: Callable, *, write: bool = False) -> Any:
        """Chuẩn hóa lỗi mà không lộ URI, mật khẩu hoặc nội dung câu hỏi."""
        try:
            timeout = (
                max(30, self.settings.neo4j_query_timeout_seconds)
                if write
                else self.settings.neo4j_query_timeout_seconds
            )
            bounded_action = unit_of_work(timeout=timeout)(action)
            with self.driver.session(database=self.settings.neo4j_database) as session:
                return (
                    session.execute_write(bounded_action)
                    if write
                    else session.execute_read(bounded_action)
                )
        except AuthError as exc:
            raise ServiceError("Neo4j từ chối thông tin đăng nhập.", "neo4j_auth_failed") from exc
        except (DriverError, Neo4jError, OSError) as exc:
            raise ServiceError(
                "Neo4j không khả dụng hoặc truy vấn vượt thời gian cho phép.",
                "neo4j_unavailable",
            ) from exc

    def read(self, text: str, parameters: dict | None = None) -> list[dict]:
        """Đọc đầy đủ kết quả trước khi đóng session."""
        return self.transaction(lambda tx: tx.run(self.query(text), parameters or {}).data())

    def close(self) -> None:
        """Giải phóng toàn bộ connection khi ứng dụng shutdown."""
        self.driver.close()


_connections: dict[str, Neo4jConnection] = {}
_lock = threading.Lock()


def get_connection(settings: Settings) -> Neo4jConnection:
    """Không dùng khóa cache chứa mật khẩu dạng rõ và không tạo driver mỗi request."""
    key = fingerprint(
        [
            settings.neo4j_uri,
            settings.neo4j_user,
            settings.neo4j_password,
            settings.neo4j_database,
            settings.neo4j_connection_timeout_seconds,
            settings.neo4j_query_timeout_seconds,
            settings.neo4j_pool_size,
        ]
    )
    with _lock:
        if key not in _connections:
            _connections[key] = Neo4jConnection(settings)
        return _connections[key]


def close_connections() -> None:
    """Đóng pool đồng thời xóa cache để ứng dụng có thể khởi động lại trong test."""
    with _lock:
        for connection in _connections.values():
            connection.close()
        _connections.clear()
