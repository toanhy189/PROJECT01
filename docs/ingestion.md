# Document Ingestion Pipeline

Pipeline tiếp tục dùng BeautifulSoup, PyMuPDF, Custom Chunking, Gemini Embedding
và ChromaDB. Không đổi FastAPI, LangGraph hoặc mô hình PyTorch.
Đối chiếu code ngày **03/11/2026**. Phần kiểm chứng cuối bài là kết quả của đợt sửa
ingestion ngày 01/11, không phải số lượng test toàn dự án hiện tại.

## Định dạng hỗ trợ thực tế

| Đầu vào | Cách xử lý | Phạm vi |
| --- | --- | --- |
| Website NIDDK | BeautifulSoup, vùng nội dung bài viết | Giữ thứ tự DOM, heading h1–h6, danh sách, caption, tham khảo, bảng và chú thích bảng |
| PDF có text | PyMuPDF `get_text(sort=True)` | Giữ thứ tự trang; sắp text theo vị trí trong trang; lưu tổng số trang |
| DOCX | python-docx 1.2.0 | Paragraph và bảng theo thứ tự; heading/style kế thừa; ô gộp và bảng lồng |
| TXT | Python UTF-8/UTF-8 BOM | Giữ đoạn và nội dung lặp; từ chối byte sai encoding, không thay ký tự âm thầm |
| Markdown | Python UTF-8/UTF-8 BOM | Giữ nội dung; chunker nhận heading ATX `#` đến `######` |

DOCX/TXT/PDF được đọc trực tiếp vào bộ nhớ, không tạo Markdown trung gian. Bản
Markdown của website vẫn được lưu như trước để kiểm tra và đối chiếu nguồn.
`download_sources` chỉ cập nhật đường dẫn `.md`, không ghi đè tệp DOCX/PDF/TXT
được import thủ công trong manifest.

## Những lỗi đã sửa

- Không xóa toàn bộ `<aside>`: trước đây làm mất tham khảo và điều kiện bên dưới
  bảng xét nghiệm. Chú thích xét nghiệm sát bảng được giữ cùng chunk bảng.
- Giữ đúng cấp heading thay vì chuyển mọi heading thành `##`.
- Duyệt nội dung theo thứ tự DOM; lấy cả văn bản trực tiếp trong container và
  caption. Mỗi phần tử được đọc một lần, tránh lặp do duyệt cả cha và con.
- Chỉ loại mục lục khi nhãn `In this section:` đi cùng danh sách liên kết đến
  các heading có thật trong bài. Không khử trùng toàn cục các câu y khoa.
- Giữ khoảng trắng inline gốc, tránh thêm khoảng trắng trước dấu câu. Giữ thẻ
  `<sup>`/`<sub>` để không nhầm chỉ số/mũ với giá trị số bình thường.
- Chuyển bảng HTML/DOCX thành Markdown có hàng/cột, giữ ô nhiều dòng và escape
  dấu `|`. Ô HTML có rowspan/colspan được mở rộng theo lưới.
- DOCX dùng `iter_inner_content()` để giữ đúng thứ tự paragraph/bảng; không đọc
  hết paragraph rồi mới nối bảng vào cuối.

## Cấu trúc đầu ra và metadata

Giữ `Document.text` để tương thích các thành phần đang dùng; không đổi tên thành
`content`. `load_document()` chuẩn hóa kết quả parser về cùng dataclass. Các hàm
parser bên trong trả văn bản, riêng PDF trả thêm metadata; chunker nhận `Document`:

```python
Document(
    document_id="niddk-tests",
    title="NIDDK — Xét nghiệm và chẩn đoán",
    source_url="https://www.niddk.nih.gov/health-information/diabetes/overview/tests-diagnosis",
    text="...",
    source_type="md",
    metadata={},
)
```

`source_type` là định dạng tệp parser đọc (`pdf`, `docx`, `txt`, `md`); bài web
đã lưu dưới dạng Markdown có `source_type=md`, URL gốc vẫn giữ nguyên.
Adapter wiki riêng tạo `Document` với `source_type=html` và metadata revision;
`load_document()` chưa nhận HTML bất kỳ từ tệp local. Wiki chưa được tải/xuất bản thật.
PDF bổ sung `metadata.page_count`. Chưa gắn số trang cho từng chunk, vì chunk
hiện tại có thể gom nội dung qua ranh giới trang; không tạo số trang giả.

Metadata chunk giữ đủ `document_id`, `chunk_id`, `title`, `section`, `source_url`;
bổ sung `source_type` và `section_path` để giữ đường dẫn heading cha/con.
Metadata tài liệu có giá trị scalar được chuyển tiếp sang chunk.

## Custom Chunking

Giữ thuật toán đóng gói theo câu, ước lượng token bằng ký tự và overlap bằng câu
nguyên vẹn. Chỉ sửa các lỗi cụ thể:

- Heading không có dòng trống vẫn được nhận diện và không làm mất đoạn kế tiếp.
- Giữ ranh giới đoạn văn trong chunk; không nối mọi đoạn bằng một dấu cách.
- Giữ bảng nguyên khối để không cắt giá trị khỏi header/cột. Bảng và câu quá dài
  có thể vượt mục tiêu mềm 500 token; không cắt tùy tiện dữ liệu y khoa.
- Section mới không nhận overlap từ section trước. Bảng không bị lặp hàng để tạo
  overlap. Cấu hình mặc định vẫn là 500 token / tối đa 50 token overlap.

## Kiểm tra và index lặp an toàn

Kiểm tra loader/chunk offline, không cần key và không mở ChromaDB:

```powershell
.\.venv\Scripts\python -X utf8 -m ingestion.index_documents --check-only
```

Chỉ kiểm tra hoặc index một số tài liệu:

```powershell
.\.venv\Scripts\python -X utf8 -m ingestion.index_documents --check-only --document-id niddk-tests
.\.venv\Scripts\python -X utf8 -m ingestion.index_documents --document-id niddk-tests
```

Lệnh index mặc định kiểm tra các mục trong manifest nhưng chỉ gọi embedding khi
ID/nội dung/metadata chunk khác bản đang lưu. Tài liệu không đổi được báo
`unchanged`; không gọi Gemini cho tài liệu đó. `documents`/`chunks` đếm phần đã
cập nhật, `unchanged_documents` đếm phần được bỏ qua; `results` ghi từng tài liệu.
Ở chế độ `--check-only`, `documents`/`chunks` đếm phần đã kiểm tra.

Chỉ upsert tài liệu khi đã nhận đủ embedding. Sau đó xóa ID chunk cũ của chính
tài liệu đó, không xóa collection hoặc tài liệu khác. API lỗi hoặc parser không
tạo được chunk sẽ giữ bản chỉ mục trước đó. Đây không phải transaction toàn bộ
corpus; lỗi được báo theo tài liệu và có thể chạy lại.

Thiếu `GEMINI_API_KEY` thì lệnh index thật dừng với thông báo rõ ràng. Kiểm thử
dùng vector mock trong ChromaDB tạm; các báo cáo index thật dùng Gemini thật.
Xóa một mục khỏi manifest chưa tự động xóa dữ liệu của nó khỏi ChromaDB.

## Khi dùng cùng GraphRAG Neo4j

`index_documents` chỉ cập nhật ChromaDB, không tự cập nhật BM25, graph hoặc
`active.json`. Nếu thay đổi corpus đang gắn với snapshot, truy xuất nâng cao sẽ
phát hiện lệch phiên bản và quay về vector; việc index xong không có nghĩa graph
đã cập nhật. Đối chiếu lại quote/annotation trước khi công bố snapshot mới.

Để giữ collection cũ, hàm Python `publish_corpus()` nhận danh sách `Document`,
tạo collection phiên bản mới, tái sử dụng vector không đổi và kiểm tra Neo4j trước
khi chuyển con trỏ active. CLI `python -m ingestion.publish_corpus` hiện chỉ dành
cho wiki đã tải đủ; chưa có CLI publisher tổng quát cho PDF/DOCX/TXT/NIDDK.
`build_retrieval_indexes --activate` dùng cho collection đã chuẩn bị; không tải
tài liệu hoặc tạo embedding mới. Chi tiết: [neo4j_demo.md](neo4j_demo.md#migration-cập-nhật-và-rollback).

## Giới hạn còn lại

- Chưa triển khai OCR hoặc đọc ảnh. `OCRRequiredError` là điểm mở rộng để thêm
  bộ xử lý riêng sau này. Không thêm Tesseract hoặc bật OCR ngầm ở MVP.
- PDF có trang không có text, kể cả PDF trộn text/scan, bị từ chối với danh sách
  trang cần kiểm tra. Trang trắng có chủ ý cũng cần xử lý trước; không bỏ qua
  trang âm thầm. PDF mật khẩu cần mở khóa trước khi index.
- Kiểm tra trên chỉ phát hiện trang có text rỗng. Trang có một ít text và phần
  nội dung scan/ảnh còn lại chưa được tự phát hiện đầy đủ; cần kiểm tra thủ công.
- Khi bổ sung OCR, cần cấu hình tắt mặc định, kiểm tra công cụ/gói ngôn ngữ
  Việt–Anh và đối chiếu thủ công số liệu/bảng; không coi OCR là chính xác tuyệt đối.
- Chưa chuyển `.doc` bằng LibreOffice. Trả lỗi theo tài liệu, hướng dẫn chuyển
  sang DOCX bằng Word/LibreOffice và tiếp tục xử lý các tài liệu hợp lệ khác.
- DOCX chưa đọc ảnh, text box, header/footer, chú thích chân trang hoặc toàn bộ
  nội dung tracked changes. Không cam kết khôi phục layout PDF nhiều cột/bảng
  phức tạp; `sort=True` chỉ cải thiện thứ tự hình học.
- Chưa thêm parser TXT bảng mã cũ hoặc bộ splitter bên ngoài.

## File thay đổi trong đợt ingestion ngày 01/11/2026

- Loader/parser: `ingestion/document_loader.py`, `ingestion/parsers.py` (mới),
  `ingestion/html_parser.py` (mới), `ingestion/table_formatter.py` (mới).
- Tải/chia đoạn/index: `ingestion/download_sources.py`, `ingestion/chunker.py`,
  `ingestion/index_documents.py`.
- Kho vector: `backend/rag/vector_store.py`; `backend/rag/retriever.py` chỉ điều
  chỉnh type hint metadata để nhận cả số/bool trong đợt này. Các lần nâng cấp sau
  đã bổ sung graph/hybrid/fusion vào retriever; xem [architecture.md](architecture.md).
- Thư viện: `requirements.txt`, `requirements.lock.txt`; thêm `python-docx`, pip
  cài thêm dependency gián tiếp `lxml`.
- Test: `tests/test_document_parsers.py` (mới), `tests/test_source_download.py`
  (mới), `tests/test_ingestion.py`.
- Nguồn: 5 tệp `data/knowledge/{overview,symptoms,risk,prevention,tests}.md` và
  `data/knowledge/download_report.json`.
- Tài liệu/báo cáo: `README.md`, `docs/architecture.md`, `docs/evaluation.md`,
  tài liệu này, `artifacts/ingestion_quality.json`,
  `artifacts/ingestion_reindex_report.json`; dữ liệu collection Chroma hiện có.

## Kết quả kiểm chứng ngày 01/11/2026

- Toàn bộ test: **84 passed**; 6 cảnh báo DeprecationWarning đã có từ joblib/NumPy.
- Ruff trên các module/test thay đổi: đạt; compileall đạt; `pip check` không có
  dependency lỗi. Không cần build lại frontend cho thay đổi ingestion này.
- Đã đối chiếu 5 bài với HTML nguồn NIDDK: từ, số, ký hiệu được kiểm tra và thứ tự
  trong vùng bài viết khớp; 54 heading giữ đúng cấp, không còn mục lục thừa.
  Phép đối chiếu không phải đánh giá y khoa và không bao gồm ảnh/nội dung đa phương tiện.
- Chia được **58 chunk**, tất cả có metadata bắt buộc, ID duy nhất; chunk lớn nhất
  476 token ước lượng, không có chunk vượt mục tiêu 500 trong corpus này.
- Đã cập nhật đúng 5 tài liệu thay đổi trong collection `diabetes_knowledge` cũ,
  dùng Gemini thật: **5 request embedding / 58 đoạn**. Không xóa collection.
- Chroma từ 55 thành 58 chunk; không còn chunk dư, không thiếu hoặc sai metadata;
  vector 768 chiều, hữu hạn, chuẩn hóa L2.
- Lần chạy tiếp: **0 tài liệu cập nhật, 5 không đổi, 0 request embedding**.
  Không cần reindex thêm nếu nội dung/cấu hình hiện tại chưa thay đổi.
- Cả 10 reference quote vẫn có trong corpus sau sửa. Chưa chạy lại benchmark
  sinh câu trả lời bằng LLM; metrics RAG trước đó thuộc corpus 55 chunk.

Báo cáo máy đọc được:
[chất lượng trích xuất](../artifacts/ingestion_quality.json),
[reindex và kiểm tra lặp](../artifacts/ingestion_reindex_report.json).
Các test mới bao phủ PDF text/thiếu text, DOCX heading/bảng/ô gộp/bảng lồng,
TXT/Markdown/BOM/lỗi encoding, heading lồng nhau, câu lặp, bảng/chú thích,
overlap và cập nhật chọn lọc/giữ chỉ mục khi API lỗi.
