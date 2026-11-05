"""Fixture dùng chung cho các bài kiểm thử, không chứa bệnh án thật."""

from pathlib import Path

import pytest

from backend.core.config import Settings
from backend.rag.vector_store import VectorStore
from ingestion.chunker import Chunk


@pytest.fixture
def feature_dict():
    """Tạo input minh họa hợp lệ đủ 21 trường, chỉ phục vụ kiểm thử phần mềm."""
    return {
        "HighBP": 0,
        "HighChol": 0,
        "CholCheck": 1,
        "BMI": 25.0,
        "Smoker": 0,
        "Stroke": 0,
        "HeartDiseaseorAttack": 0,
        "PhysActivity": 1,
        "Fruits": 1,
        "Veggies": 1,
        "HvyAlcoholConsump": 0,
        "AnyHealthcare": 1,
        "NoDocbcCost": 0,
        "GenHlth": 2,
        "MentHlth": 0,
        "PhysHlth": 0,
        "DiffWalk": 0,
        "Sex": 0,
        "Age": 5,
        "Education": 5,
        "Income": 6,
    }


@pytest.fixture
def graph_corpus(tmp_path: Path):
    """Tạo thực thể/quan hệ giả chỉ dùng kiểm thử phần mềm, không làm KB y khoa."""
    settings = Settings(
        chroma_dir=tmp_path / "chroma",
        retrieval_index_dir=tmp_path / "indexes",
        enable_graph_retrieval=True,
        enable_hybrid_search=True,
        graph_backend="networkx",
    )
    rows = []
    for cid, text in [
        ("a", "Alpha assesses Beta in this software test."),
        ("b", "Gamma is associated with Beta in this software test."),
        ("c", "Alpha can assess Beta in another software test."),
    ]:
        rows.append(
            {
                "chunk_id": cid,
                "text": text,
                "metadata": {
                    "chunk_id": cid,
                    "document_id": cid,
                    "title": "Software test",
                    "section": "Test",
                    "source_url": "https://www.niddk.nih.gov/test",
                },
            }
        )
    ontology = {
        "entities": [
            {"entity_id": "alpha", "name": "Alpha", "entity_type": "test", "aliases": ["an pha"]},
            {"entity_id": "beta", "name": "Beta", "entity_type": "condition", "aliases": []},
            {"entity_id": "gamma", "name": "Gamma", "entity_type": "risk_factor", "aliases": []},
        ]
    }
    annotations = [
        {
            "subject": subject,
            "predicate": predicate,
            "object": "beta",
            "document_id": cid,
            "quote": rows[index]["text"],
            "status": "source_checked",
            "checked_by": "unit_test",
        }
        for index, (subject, predicate, cid) in enumerate(
            [
                ("alpha", "USED_TO_ASSESS", "a"),
                ("gamma", "RISK_FACTOR_FOR", "b"),
                ("alpha", "USED_TO_ASSESS", "c"),
            ]
        )
    ]
    store = VectorStore(settings)
    for index, row in enumerate(rows):
        vector = [0.0] * 768
        vector[0 if index == 0 else 1] = 1.0
        store.replace_document(
            row["metadata"]["document_id"],
            [Chunk(row["chunk_id"], row["text"], row["metadata"])],
            [vector],
        )
    return settings, rows, ontology, annotations, store
