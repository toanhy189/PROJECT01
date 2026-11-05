"""Không công bố báo cáo hoặc đổi snapshot khi nguồn gốc chưa hợp lệ."""

import json

import pytest

from backend.core.config import get_settings
from evaluation.inspect_model import inspect_model
from ingestion.activate_snapshot import activate_snapshot


def test_inspection_rejects_other_dataset_before_loading_model(tmp_path):
    """Không ghi báo cáo ảnh hưởng từ CSV khác phiên bản huấn luyện."""
    csv = tmp_path / "different.csv"
    csv.write_text("different dataset", encoding="utf-8")
    with pytest.raises(ValueError, match="phiên bản"):
        inspect_model(csv, get_settings().artifact_dir)


def test_invalid_snapshot_does_not_change_active_pointer(tmp_path):
    """ID sai bị chặn trước mọi thay đổi con trỏ hoặc lời gọi Neo4j."""
    active = tmp_path / "active.json"
    original = {"snapshot_id": "original"}
    active.write_text(json.dumps(original), encoding="utf-8")
    settings = get_settings().model_copy(update={"retrieval_index_dir": tmp_path})
    with pytest.raises(ValueError, match="Snapshot ID"):
        activate_snapshot(settings, "../../outside")
    assert json.loads(active.read_text("utf-8")) == original
