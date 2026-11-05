"""Kiểm thử nháp Gemini bằng client mock, không giả làm tri thức đã duyệt."""

import json
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from ingestion.extract_graph import extract_drafts


def test_extraction_caches_drafts_and_rejects_unknown_entities(graph_corpus, tmp_path, monkeypatch):
    """Chỉ quote/entity hợp lệ được lưu làm nháp; cache đầy không cần tạo client lại."""
    settings, rows, ontology, _, _ = graph_corpus
    snapshot = SimpleNamespace(rows=rows, graph=SimpleNamespace(entities=ontology["entities"]))
    monkeypatch.setattr("ingestion.extract_graph.get_settings", lambda: settings)
    monkeypatch.setattr("ingestion.extract_graph.load_active_snapshot", lambda _: snapshot)
    good = {
        "subject": "alpha",
        "predicate": "USED_TO_ASSESS",
        "object": "beta",
        "quote": rows[0]["text"],
        "qualifiers": "Software test only",
        "polarity": "positive",
    }
    client = Mock()
    client.models.generate_content.return_value = SimpleNamespace(
        text=json.dumps({"relations": [good, {**good, "subject": "unknown"}]})
    )
    context = Mock()
    context.__enter__ = Mock(return_value=client)
    context.__exit__ = Mock(return_value=False)
    factory = Mock(return_value=context)
    monkeypatch.setattr("ingestion.extract_graph.make_client", factory)
    path = tmp_path / "drafts.json"
    first = extract_drafts({"a"}, path)
    second = extract_drafts({"a"}, path)
    assert first["api_calls"] == 1 and second["api_calls"] == 0
    factory.assert_called_once()
    record = next(iter(json.loads(path.read_text(encoding="utf-8"))["chunks"].values()))
    assert record["rejected"] == 1 and record["drafts"][0]["status"] == "draft"
    assert record["drafts"][0]["checked_by"] == ""
    assert client.models.generate_content.call_args.kwargs["config"].response_json_schema


def test_extraction_unknown_document_does_not_call_gemini(graph_corpus, tmp_path, monkeypatch):
    """ID sai phải dừng trước khi tạo client hoặc gọi API."""
    settings, rows, ontology, _, _ = graph_corpus
    monkeypatch.setattr("ingestion.extract_graph.get_settings", lambda: settings)
    monkeypatch.setattr(
        "ingestion.extract_graph.load_active_snapshot",
        lambda _: SimpleNamespace(rows=rows, graph=SimpleNamespace(entities=ontology["entities"])),
    )
    factory = Mock()
    monkeypatch.setattr("ingestion.extract_graph.make_client", factory)
    with pytest.raises(ValueError, match="Document ID"):
        extract_drafts({"unknown"}, tmp_path / "drafts.json")
    factory.assert_not_called()
