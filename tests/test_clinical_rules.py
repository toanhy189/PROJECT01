"""Kiểm tra thông số người dùng, nguồn có phiên bản và quy tắc BMI."""

from shutil import copytree
from unittest.mock import Mock

import pytest

from backend.core.config import ROOT, get_settings
from backend.graph.workflow import Workflow
from backend.knowledge.clinical_rules import ClinicalRules
from backend.knowledge.measurements import bmi_input, scenario_change
from backend.llm.llm_provider import Claim, GeneratedAnswer
from backend.rag.semantic_validator import validate_clinical_meaning
from backend.schemas.features import PatientFeatures


@pytest.mark.parametrize(
    "value,label",
    [
        (18.5, "khỏe mạnh"),
        (25, "thừa cân"),
        (30, "béo phì"),
        (40, "béo phì nặng"),
        (59, "béo phì nặng"),
    ],
)
def test_bmi_boundaries_have_real_source(value, label):
    """Dùng bảng nguồn thật, không gán số người dùng thành số trong tài liệu."""
    observation = bmi_input(f"BMI {value} của mình cao không, mình 25 tuổi?")
    result = ClinicalRules().assess_bmi(observation)
    assert not result.needs_clarification
    assert label in result.answer
    assert len(result.citations) == 2
    assert result.source_unchanged()
    assert result.details["origin"] == "question"
    assert result.details["scope"] == "age_20_plus"


def test_unknown_age_and_comma_decimal():
    """Thiếu tuổi thì giải thích có điều kiện, không coi mã tuổi 18–24 là đủ."""
    result = ClinicalRules().assess_bmi(bmi_input("BMI 30,5 của mik có quá cao k"))
    assert "Nếu bạn từ 20 tuổi" in result.answer
    assert result.details["value"] == 30.5


@pytest.mark.parametrize(
    "query",
    [
        "BMI 59, tôi 17 tuổi",
        "BMI 59, tôi đang mang thai",
        "BMI -5 có cao không",
        "BMI 22 và BMI 59 có sao không",
    ],
)
def test_scope_invalid_or_multiple_values_need_clarification(query):
    """Không áp dụng bảng người lớn sai đối tượng hoặc đoán giữa nhiều giá trị."""
    assert ClinicalRules().assess_bmi(bmi_input(query)).needs_clarification


def test_conflict_with_form_and_age_group(feature_dict):
    """Không âm thầm sửa BMI trong form hoặc suy ra tuổi chính xác từ nhóm rộng."""
    features = PatientFeatures(**(feature_dict | {"BMI": 21, "Age": 1}))
    conflict = ClinicalRules().assess_bmi(bmi_input("BMI 59 có cao không?", features))
    assert conflict.needs_clarification
    assert "21" in conflict.answer and "59" in conflict.answer
    result = ClinicalRules().assess_bmi(bmi_input("BMI của mình có cao không?", features))
    assert "Nếu bạn từ 20 tuổi" in result.answer


def test_changed_source_invalidates_rule(tmp_path):
    """Nguồn thay đổi phải dừng quy tắc thay vì dùng lại mốc không kiểm chứng."""
    directory = tmp_path / "knowledge"
    copytree(ROOT / "data/knowledge", directory)
    rules = ClinicalRules(directory)
    observation = bmi_input("BMI 59 có cao không")
    result = rules.assess_bmi(observation)
    assert not result.needs_clarification
    with (directory / "bmi.md").open("a", encoding="utf-8") as stream:
        stream.write("\nChanged source.")
    assert not result.source_unchanged()
    assert rules.assess_bmi(observation).needs_clarification


def test_workflow_bmi_uses_no_gemini_and_followup_isolated(feature_dict):
    """Quy tắc và mô phỏng chạy thật; không lưu hồ sơ vào workflow dùng chung."""
    llm, retriever = Mock(), Mock()
    workflow = Workflow(get_settings(), llm=llm, retriever=retriever)
    result = workflow.run("test-bmi", "BMI 59 của mik có quá cao k")
    assert result.safety_status == "passed"
    assert result.measurement_result["value"] == 59
    llm.generate.assert_not_called()
    retriever.retrieve.assert_not_called()
    features = PatientFeatures(**feature_dict)
    scenario = workflow.run("test-scenario", "Nếu giảm 3 thì sao?", features, "BMI")
    assert scenario.scenario_result["modified_features"]["BMI"] == features.BMI - 3
    assert features.BMI == feature_dict["BMI"]
    isolated = workflow.run("other-session", "Nếu giảm 3 thì sao?")
    assert isolated.safety_status == "fallback"
    assert isolated.scenario_result is None


@pytest.mark.parametrize(
    "text,valid",
    [
        ("Để chẩn đoán tiểu đường, A1C nằm từ 5,7% đến 6,4%.", False),
        ("Để chẩn đoán bệnh tiểu đường, glucose lúc đói từ 100 đến 125 mg/dL.", False),
        ("Khoảng tiền tiểu đường có A1C từ 5,7% đến 6,4%.", True),
        ("Để chẩn đoán tiểu đường, A1C từ 6,5% trở lên.", True),
    ],
)
def test_semantic_guard_rejects_swapped_test_ranges(text, valid):
    """Chặn lỗi diễn giải cụ thể đã quan sát trong giao diện."""
    draft = GeneratedAnswer(
        insufficient_evidence=False,
        claims=[
            Claim(
                text=text, citation_ids=["S1"], supporting_quotes={"S1": "Software test evidence."}
            )
        ],
    )
    assert validate_clinical_meaning(draft)[0] is valid


def test_followup_requires_context_and_valid_unit():
    """Không đoán chỉ số cần giảm hoặc coi kg là đơn vị BMI."""
    assert scenario_change("giảm 3") == (None, True)
    assert scenario_change("giảm 3", "BMI") == (-3, False)
    assert scenario_change("BMI giảm 3 kg") == (None, True)
