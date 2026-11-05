"""Kiểm thử quy tắc liều thuốc, đơn vị xét nghiệm và embedding không hợp lệ."""

import pytest

from backend.agents.safety import unsafe_answer
from backend.core.config import Settings
from backend.core.errors import ServiceError
from backend.rag.embedding_service import EmbeddingService


@pytest.mark.parametrize("text", ["Hãy uống 500 mg metformin.", "Bạn nên tiêm 10 đơn vị insulin."])
def test_block_medication_doses(text):
    """Phát hiện một số hướng dẫn liều thuốc bằng mg hoặc đơn vị insulin."""
    assert unsafe_answer(text)


def test_glucose_units_are_not_treated_as_medication_dose():
    """Không nhầm nồng độ xét nghiệm mg/dL thành một liều thuốc."""
    assert not unsafe_answer("Nguồn tài liệu đề cập glucose máu 126 mg/dL.")


@pytest.mark.parametrize("values", [[0.0] * 768, [1.0] * 10, [float("nan")] * 768])
def test_reject_invalid_embedding_shape_and_values(values):
    """Từ chối vector sai chiều, toàn số không hoặc có NaN."""
    from types import SimpleNamespace
    from unittest.mock import Mock

    client = Mock()
    client.models.embed_content.return_value = SimpleNamespace(
        embeddings=[SimpleNamespace(values=values)]
    )
    with pytest.raises(ServiceError):
        EmbeddingService(Settings(), client).embed(["Kiểm thử"])
