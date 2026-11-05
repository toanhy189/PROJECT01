"""Lỗi dịch vụ có mã nhận diện và thông báo được phép trả xuống API."""


class ServiceError(RuntimeError):
    """Lỗi dịch vụ có thông báo an toàn để trả cho người dùng."""

    def __init__(self, message: str, code: str = "service_unavailable") -> None:
        """Gắn mã lỗi để log và thông báo sạch để hiển thị cho người dùng."""
        super().__init__(message)
        self.code = code
