"""Kiểm thử parser bằng tài liệu nhỏ, không dùng dữ liệu y khoa giả làm nguồn thật."""

from pathlib import Path

import pymupdf
import pytest
from docx import Document as create_docx
from docx.enum.style import WD_STYLE_TYPE

from ingestion.chunker import chunk_document, estimate_tokens
from ingestion.document_loader import Document, load_document
from ingestion.html_parser import extract_article
from ingestion.parsers import OCRRequiredError

SOURCE_URL = "https://www.niddk.nih.gov/health-information/diabetes"


def load_sample(path: Path) -> Document:
    """Đọc mẫu thử với cùng metadata nguồn đã duyệt."""
    return load_document(path, "sample", "Tài liệu kiểm thử", SOURCE_URL)


@pytest.mark.parametrize("extension", ["md", "txt"])
def test_utf8_bom_paragraphs_and_repeated_content(tmp_path: Path, extension: str) -> None:
    """Giữ tiếng Việt, đơn vị, đoạn văn và câu lặp có thể mang ý nghĩa y khoa."""
    text = "Đoạn đầu: 6.5% và 126 mg/dL.\n\nKhông tự chẩn đoán.\n\nKhông tự chẩn đoán."
    path = tmp_path / f"sample.{extension}"
    path.write_text(text, encoding="utf-8-sig")
    document = load_sample(path)
    assert document.text == text
    assert document.source_type == extension
    assert document.source_url == SOURCE_URL
    chunks = chunk_document(document)
    assert "\n\n" in chunks[0].text
    assert sum(chunk.text.count("Không tự chẩn đoán.") for chunk in chunks) == 2


@pytest.mark.parametrize("extension", ["md", "txt"])
def test_invalid_encoding_does_not_replace_characters(tmp_path: Path, extension: str) -> None:
    """Không âm thầm đổi byte lỗi thành ký tự thay thế rồi đưa vào embedding."""
    path = tmp_path / f"bad.{extension}"
    path.write_bytes(b"invalid \xff encoding")
    with pytest.raises(ValueError, match="UTF-8"):
        load_sample(path)


def test_docx_interleaves_headings_paragraphs_and_tables(tmp_path: Path) -> None:
    """Bảng nằm đúng giữa hai đoạn, giữ ô nhiều dòng và heading kế thừa."""
    docx = create_docx()
    docx.add_heading("Mục cha", level=1)
    docx.add_paragraph("Trước bảng.")
    table = docx.add_table(rows=3, cols=2)
    for row, values in zip(
        table.rows,
        [("Chỉ số", "Giá trị"), ("A1C", "6.5%"), ("Glucose", "126 mg/dL\nGhi chú | thử nghiệm")],
    ):
        for cell, value in zip(row.cells, values):
            cell.text = value
    style = docx.styles.add_style("Custom subheading", WD_STYLE_TYPE.PARAGRAPH)
    style.base_style = docx.styles["Heading 2"]
    docx.add_paragraph("Mục con", style=style)
    docx.add_paragraph("Sau bảng.")
    path = tmp_path / "sample.docx"
    docx.save(path)
    document = load_sample(path)
    assert document.source_type == "docx"
    assert "# Mục cha" in document.text and "## Mục con" in document.text
    assert document.text.index("Trước bảng.") < document.text.index("| Chỉ số | Giá trị |")
    assert document.text.index("126 mg/dL") < document.text.index("Sau bảng.")
    assert "| A1C | 6.5% |" in document.text
    assert "126 mg/dL<br>Ghi chú \\| thử nghiệm" in document.text
    chunks = chunk_document(document)
    table_chunk = next(chunk for chunk in chunks if "| A1C |" in chunk.text)
    assert table_chunk.text.startswith("| Chỉ số | Giá trị |\n")
    assert "126 mg/dL" in table_chunk.text
    assert chunks[-1].metadata["section"] == "Mục con"
    assert chunks[-1].metadata["section_path"] == "Mục cha > Mục con"


def test_docx_merged_cells_and_nested_table_are_not_lost(tmp_path: Path) -> None:
    """Giữ văn bản ô gộp và nội dung bảng con đúng thứ tự trong ô."""
    docx = create_docx()
    table = docx.add_table(rows=2, cols=2)
    table.cell(0, 0).merge(table.cell(0, 1)).text = "Tiêu đề gộp"
    cell = table.cell(1, 0)
    cell.text = "Trước bảng con"
    nested = cell.add_table(rows=1, cols=1)
    nested.cell(0, 0).text = "Nội dung bảng con"
    cell.add_paragraph("Sau bảng con")
    table.cell(1, 1).text = "Ô bên phải"
    path = tmp_path / "nested.docx"
    docx.save(path)
    text = load_sample(path).text
    assert text.count("Tiêu đề gộp") == 1
    assert text.index("Trước bảng con") < text.index("Nội dung bảng con")
    assert text.index("Nội dung bảng con") < text.index("Sau bảng con")
    assert "Ô bên phải" in text


def test_pdf_text_order_and_metadata(tmp_path: Path) -> None:
    """Text chèn ngược thứ tự vẫn được đọc theo vị trí trên trang."""
    path = tmp_path / "text.pdf"
    with pymupdf.open() as pdf:
        page = pdf.new_page()
        page.insert_text((72, 120), "Second paragraph.")
        page.insert_text((72, 72), "First paragraph.")
        pdf.save(path)
    document = load_sample(path)
    assert document.text.index("First paragraph.") < document.text.index("Second paragraph.")
    assert document.metadata["page_count"] == 1
    assert document.source_type == "pdf"
    assert chunk_document(document)[0].metadata["page_count"] == 1


@pytest.mark.parametrize("mixed", [False, True])
def test_pdf_missing_text_is_not_silently_indexed(tmp_path: Path, mixed: bool) -> None:
    """Chặn PDF rỗng và PDF có trang scan xen kẽ, không chấp nhận nội dung thiếu."""
    path = tmp_path / "scan.pdf"
    with pymupdf.open() as pdf:
        if mixed:
            pdf.new_page().insert_text((72, 72), "A page with text.")
        pdf.new_page()
        pdf.save(path)
    with pytest.raises(OCRRequiredError, match="OCR") as error:
        load_sample(path)
    assert f"trang {2 if mixed else 1}" in str(error.value)


@pytest.mark.parametrize("extension", ["txt", "md", "docx"])
def test_empty_documents_are_rejected(tmp_path: Path, extension: str) -> None:
    """Không đưa tài liệu trống vào chunking hoặc thay thế chỉ mục cũ."""
    path = tmp_path / f"empty.{extension}"
    if extension == "docx":
        create_docx().save(path)
    else:
        path.write_text(" \n\n ", encoding="utf-8")
    with pytest.raises(ValueError, match="rỗng"):
        load_sample(path)


def test_legacy_doc_is_explicitly_unsupported(tmp_path: Path) -> None:
    """DOC cũ cần chuyển đổi ngoài pipeline hiện tại."""
    path = tmp_path / "legacy.doc"
    path.write_bytes(b"legacy")
    with pytest.raises(ValueError, match="LibreOffice"):
        load_sample(path)


def test_corrupt_docx_is_a_clear_parsing_error(tmp_path: Path) -> None:
    """Tệp DOCX hỏng trả lỗi có thể tổng hợp theo tài liệu, không làm dừng pipeline."""
    path = tmp_path / "broken.docx"
    path.write_bytes(b"not a DOCX package")
    with pytest.raises(ValueError, match="DOCX"):
        load_sample(path)


def test_nested_headings_without_blank_lines_keep_all_paragraphs() -> None:
    """Heading liền đoạn không được nuốt nội dung hoặc gắn section sai."""
    document = Document(
        "x",
        "Tài liệu",
        SOURCE_URL,
        "# Cha\nĐoạn thứ nhất.\n## Con\nĐoạn thứ hai.\n### Cháu\nĐoạn thứ ba."
        "\n## Con khác\nĐoạn cuối.",
    )
    chunks = chunk_document(document)
    assert [chunk.text for chunk in chunks] == [
        "Đoạn thứ nhất.",
        "Đoạn thứ hai.",
        "Đoạn thứ ba.",
        "Đoạn cuối.",
    ]
    assert chunks[2].metadata["section_path"] == "Cha > Con > Cháu"
    assert chunks[3].metadata["section_path"] == "Cha > Con khác"
    assert all(chunk.metadata["source_url"] == SOURCE_URL for chunk in chunks)


def test_sentence_overlap_size_and_section_boundaries() -> None:
    """Overlap giữ câu nguyên vẹn, nằm trong ngân sách và không tràn sang section mới."""
    sentences = [f"Sentence {index} has enough words for this test." for index in range(12)]
    document = Document(
        "x",
        "Tài liệu",
        SOURCE_URL,
        "# First\n\n" + " ".join(sentences) + "\n\n# Second\n\nNew section.",
    )
    chunks = chunk_document(document, max_tokens=40, overlap_tokens=12)
    assert all(estimate_tokens(chunk.text) <= 40 for chunk in chunks)
    assert chunks[0].text.endswith(sentences[2])
    assert chunks[1].text.startswith(sentences[2])
    assert chunks[-1].text == "New section."
    assert chunks[-1].metadata["section"] == "Second"
    assert chunks == chunk_document(document, max_tokens=40, overlap_tokens=12)


def test_large_table_stays_intact_with_medical_units() -> None:
    """Bảng vượt mục tiêu mềm vẫn giữ header, hàng và số liệu thay vì cắt tùy tiện."""
    table = "| Label | Value |\n| --- | --- |\n" + "| A1C test. | 6.5% |\n" * 10
    document = Document("x", "Tài liệu", SOURCE_URL, "# Results\n\n" + table)
    chunks = chunk_document(document, max_tokens=20, overlap_tokens=0)
    assert len(chunks) == 1
    assert chunks[0].text == table.strip()


def test_html_references_captions_order_and_confirmed_toc() -> None:
    """Giữ tham khảo/cảnh báo trong aside và bỏ đúng mục lục có đích heading thật."""
    html = """
    <nav>Menu ngoài bài</nav><div class="health-detail-content">
    <p><strong>In this section:</strong></p><ul><li><a href="#a">Section A</a></li></ul>
    <h2 id="a">Section A</h2><p>Before <a href="/x">inline link</a>, keep punctuation.</p>
    <h3>Subsection</h3><div>Direct text.<p>Important repeated warning.</p></div>
    <p>Important repeated warning.</p><figure><img src="x"><figcaption>Caption text.</figcaption>
    </figure><aside><p>Do not diagnose yourself.</p></aside>
    <h2>References</h2><aside class="references"><p>[1] A source, 2022.</p></aside>
    <footer>Footer text</footer></div>
    """
    text = extract_article(html)
    assert "In this section:" not in text
    assert "Menu ngoài bài" not in text and "Footer text" not in text
    assert "## Section A" in text and "### Subsection" in text
    assert "Before inline link, keep punctuation." in text
    assert text.count("Important repeated warning.") == 2
    assert text.index("Direct text.") < text.index("Caption text.")
    assert text.index("Caption text.") < text.index("Do not diagnose yourself.")
    assert text.endswith("[1] A source, 2022.")


def test_html_nested_lists_are_emitted_once_and_non_toc_links_stay() -> None:
    """Không nhân đôi phần tử con và không nhầm danh sách kiến thức thành mục lục."""
    text = extract_article("""<article><p>In this section:</p>
        <ul><li><a href="/external">Important link</a></li></ul>
        <ul><li><p>Parent warning.</p><ul><li>Child warning.</li></ul></li></ul></article>""")
    assert "Important link" in text
    assert "In this section:" in text
    assert text.count("Parent warning.") == 1
    assert text.count("Child warning.") == 1


def test_html_table_preserves_rows_spans_and_notes() -> None:
    """Ô gộp không làm lệch cột; ghi chú về điều kiện xét nghiệm được giữ sau bảng."""
    text = extract_article("""<article><h2>Results</h2><table>
        <tr><th rowspan="2">Diagnosis</th><th colspan="2">Glucose</th></tr>
        <tr><th>Fasting</th><th>Random</th></tr>
        <tr><td>Sample</td><td>126 mg/dL</td><td>200 mg/dL</td></tr></table>
        <aside class="references"><p>* 2 hours<br>Source: Test</p></aside></article>""")
    assert "| Diagnosis | Glucose | Glucose |" in text
    assert "| Diagnosis | Fasting | Random |" in text
    assert "| Sample | 126 mg/dL | 200 mg/dL |" in text
    assert text.index("200 mg/dL") < text.index("* 2 hours\nSource: Test")
    chunks = chunk_document(Document("x", "Test", SOURCE_URL, text))
    table_chunk = next(chunk for chunk in chunks if "126 mg/dL" in chunk.text)
    assert "* 2 hours\nSource: Test" in table_chunk.text
    assert text.count("Source: Test") == 1


def test_html_subscript_superscript_and_missing_article() -> None:
    """Giữ ý nghĩa chỉ số/mũ và không dùng cả trang khi selector bài viết thất bại."""
    text = extract_article("<article><p>m<sup>2</sup>, H<sub>2</sub>O</p></article>")
    assert text == "m<sup>2</sup>, H<sub>2</sub>O"
    with pytest.raises(ValueError, match="selector"):
        extract_article("<html><nav>Menu</nav></html>")
