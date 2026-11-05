"""Kiểm thử timeout/nạp lười bằng process mock, không tải model trong unit test."""

from unittest.mock import Mock

from backend.core.config import Settings
from backend.rag.models import Evidence
from backend.rag.reranker import LocalReranker


def candidates() -> list[Evidence]:
    """Tạo hai ứng viên kiểm thử có thứ tự RRF ban đầu cố định."""
    return [
        Evidence("Software A", {"chunk_id": "a"}, score=1),
        Evidence("Software B", {"chunk_id": "b"}, score=0.5),
    ]


def test_disabled_reranker_does_not_start_process(monkeypatch):
    """Tắt tính năng không được nạp model hoặc tạo worker."""
    spawn = Mock()
    monkeypatch.setattr("backend.rag.reranker.mp.get_context", spawn)
    original = candidates()
    result, status = LocalReranker(Settings(enable_reranking=False)).rerank("Test", original)
    assert result is original and status == "disabled"
    spawn.assert_not_called()


def worker_context(monkeypatch, replies, polls):
    """Mô phỏng pipe và process để kiểm tra giao thức nạp/model score."""
    context, parent, child, process = Mock(), Mock(), Mock(), Mock()
    parent.recv.side_effect = replies
    parent.poll.side_effect = polls
    context.Pipe.return_value = (parent, child)
    context.Process.return_value = process
    process.is_alive.return_value = True
    monkeypatch.setattr("backend.rag.reranker.mp.get_context", Mock(return_value=context))
    return process, parent


def test_reranker_changes_order_only_after_valid_scores(monkeypatch):
    """Điểm model xếp lại ứng viên nhưng không ghi đè distance/điểm RRF."""
    process, _ = worker_context(
        monkeypatch, [{"ready": True}, {"scores": [0.1, 0.9]}], [True, True]
    )
    reranker = LocalReranker(Settings(enable_reranking=True))
    original = candidates()
    result, status = reranker.rerank("Test", original)
    assert status == "applied" and [r.metadata["chunk_id"] for r in result] == ["b", "a"]
    assert result[0].score == 0.5 and result[0].distance is None
    reranker.close()
    process.terminate.assert_called_once()


def test_timeout_terminates_worker_and_uses_cooldown(monkeypatch):
    """Worker quá hạn bị dừng thật, lần tiếp không tạo tác vụ nền vô hạn."""
    process, _ = worker_context(monkeypatch, [{"ready": True}], [True, False])
    reranker = LocalReranker(Settings(enable_reranking=True))
    original = candidates()
    result, status = reranker.rerank("Test", original)
    assert result is original and status == "fallback_timeout_or_unavailable"
    process.terminate.assert_called_once()
    assert reranker.rerank("Test", original)[1] == "fallback_cooldown"


def test_missing_cached_model_falls_back(monkeypatch):
    """Model chưa tải không được kích hoạt hoặc tự tải ngầm khi chat."""
    process, _ = worker_context(monkeypatch, [{"error": "reranker_unavailable"}], [True])
    reranker = LocalReranker(Settings(enable_reranking=True))
    original = candidates()
    assert reranker.rerank("Test", original) == (original, "fallback_timeout_or_unavailable")
    process.terminate.assert_called_once()
