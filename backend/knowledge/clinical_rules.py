"""Đối chiếu BMI bằng quy tắc có phiên bản và đoạn nguồn được xác minh."""

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

from backend.core.config import ROOT
from backend.knowledge.measurements import BmiInput
from backend.schemas.api import Citation
from ingestion.chunker import chunk_document
from ingestion.document_loader import load_document


@dataclass(frozen=True)
class VerifiedAnswer:
    """Kết quả do công cụ backend tạo, tách khỏi claim tự sinh của Gemini."""

    answer: str
    citations: tuple[Citation, ...] = ()
    details: dict | None = None
    needs_clarification: bool = False
    source_path: Path | None = None
    source_sha256: str | None = None

    def source_unchanged(self) -> bool:
        """Không dùng lại kết quả quy tắc nếu nguồn đã đổi trong lúc xử lý."""
        if self.source_path is None:
            return True
        try:
            return hashlib.sha256(self.source_path.read_bytes()).hexdigest() == self.source_sha256
        except OSError:
            return False


class ClinicalRules:
    """Chỉ đọc dữ liệu cục bộ đã tải, không hardcode kiến thức trong prompt."""

    def __init__(self, knowledge_dir: Path = ROOT / "data/knowledge") -> None:
        """Nhận thư mục riêng để kiểm thử nguồn và phạm vi quy tắc."""
        self.knowledge_dir = knowledge_dir

    def assess_bmi(self, observation: BmiInput) -> VerifiedAnswer:
        """Phân loại khoảng BMI trong đúng phạm vi nguồn; không chẩn đoán tiểu đường."""
        if observation.reason:
            return VerifiedAnswer(observation.reason, needs_clarification=True)
        value = observation.value
        if value is None:
            return VerifiedAnswer("Hãy nêu rõ chỉ số BMI cần xét.", needs_clarification=True)
        if observation.adult is False:
            return VerifiedAnswer(
                "Bảng BMI này dành cho người từ 20 tuổi trở lên. Với trẻ em và thanh thiếu niên, "
                "cần đánh giá theo tuổi và giới tính; "
                "chưa áp dụng bảng người lớn cho chỉ số bạn nêu.",
                needs_clarification=True,
            )
        try:
            rule = json.loads((self.knowledge_dir / "clinical_rules.json").read_text("utf-8"))
            entry = next(
                item
                for item in json.loads((self.knowledge_dir / "manifest.json").read_text("utf-8"))
                if item["document_id"] == rule["document_id"]
            )
            path = (self.knowledge_dir / entry["path"]).resolve()
            if not path.is_relative_to(self.knowledge_dir.resolve()):
                raise ValueError("Đường dẫn nguồn không hợp lệ.")
            if hashlib.sha256(path.read_bytes()).hexdigest() != rule["source_sha256"]:
                raise ValueError("Nguồn đã thay đổi.")
            document = load_document(
                path, entry["document_id"], entry["title"], entry["source_url"]
            )
            chunk = next(item for item in chunk_document(document) if rule["quote"] in item.text)
            citation = Citation(citation_id="S1", quote=chunk.text, **chunk.metadata)
            diagnosis = next(
                item
                for item in json.loads((self.knowledge_dir / "manifest.json").read_text("utf-8"))
                if item["document_id"] == "niddk-tests"
            )
            diagnosis_path = (self.knowledge_dir / diagnosis["path"]).resolve()
            if not diagnosis_path.is_relative_to(self.knowledge_dir.resolve()):
                raise ValueError("Đường dẫn nguồn không hợp lệ.")
            diagnosis_doc = load_document(
                diagnosis_path,
                diagnosis["document_id"],
                diagnosis["title"],
                diagnosis["source_url"],
            )
            diagnosis_quote = (
                "Your doctor can diagnose diabetes, prediabetes, "
                "and gestational diabetes using blood tests."
            )
            diagnosis_chunk = next(
                item for item in chunk_document(diagnosis_doc) if diagnosis_quote in item.text
            )
            diagnosis_citation = Citation(
                citation_id="S2", quote=diagnosis_chunk.text, **diagnosis_chunk.metadata
            )
            category = next(
                (
                    item
                    for item in rule["categories"]
                    if item["min"] <= value and (item["max"] is None or value <= item["max"])
                ),
                None,
            )
            if category is None:
                return VerifiedAnswer(
                    "Chỉ số bạn nêu chưa thuộc khoảng có thể kết luận trực tiếp từ bảng đang có. "
                    "Hãy kiểm tra cách ghi BMI và trao đổi với nhân viên y tế; "
                    "hệ thống không tự bổ sung ngưỡng ngoài nguồn.",
                    (citation,),
                    needs_clarification=True,
                )
            origin = "từ form" if observation.origin == "form" else "trong câu hỏi"
            condition = (
                "Theo bảng NIDDK"
                if observation.adult
                else "Nếu bạn từ 20 tuổi trở lên, theo bảng NIDDK"
            )
            answer = (
                f"Bạn cung cấp BMI {value:g} ({origin}; "
                "chưa phải phép đo đã được hệ thống xác minh).\n\n"
                f"{condition}, giá trị này thuộc khoảng {category['range_label']}: "
                f"{category['label_vi']}. [S1]\n\n"
                "Đây là đối chiếu chỉ số BMI theo tài liệu, "
                "không phải kết luận bạn có mắc tiểu đường. "
                "Chẩn đoán tiểu đường cần xét nghiệm và đánh giá của nhân viên y tế. [S2]"
            )
            if value >= 40:
                answer += (
                    " Bạn nên trao đổi với nhân viên y tế "
                    "để được đánh giá đầy đủ tình trạng cân nặng."
                )
            return VerifiedAnswer(
                answer,
                (citation, diagnosis_citation),
                {
                    "rule_id": rule["rule_id"],
                    "value": value,
                    "origin": observation.origin,
                    "scope": "age_20_plus" if observation.adult else "conditional_age_20_plus",
                    "category": category["label_vi"],
                    "source_sha256": rule["source_sha256"],
                    "comparison": {"minimum": category["min"], "maximum": category["max"]},
                },
                source_path=path,
                source_sha256=rule["source_sha256"],
            )
        except (OSError, ValueError, KeyError, StopIteration):
            return VerifiedAnswer(
                "Nguồn hoặc quy tắc BMI chưa được xác minh với phiên bản tài liệu hiện tại. "
                "Hệ thống chưa phân loại chỉ số này; hãy kiểm tra nguồn trước khi thử lại.",
                needs_clarification=True,
            )
