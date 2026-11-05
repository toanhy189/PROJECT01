"""Định nghĩa kiến trúc MLP dùng chung giữa huấn luyện và suy luận."""

from torch import nn


class DiabetesMLP(nn.Sequential):
    """MLP nhận 21 đặc trưng và trả một logit cho phân loại nhị phân."""

    def __init__(self) -> None:
        """Tạo hai tầng ẩn 64 và 32 nút; không thêm sigmoid trước hàm loss."""
        super().__init__(
            nn.Linear(21, 64),
            nn.ReLU(),
            nn.Dropout(0.2),
            nn.Linear(64, 32),
            nn.ReLU(),
            nn.Linear(32, 1),
        )
