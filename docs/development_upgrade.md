# Các chức năng đã bổ sung và cách sử dụng

Đối chiếu ngày 05/11/2026. Giữ nguyên React, FastAPI, LangGraph, PyTorch,
Custom Chunking, Gemini Embedding, ChromaDB và Neo4j. Không train lại model
hoặc thay ngưỡng. ZIP giao diện được dùng làm tham khảo hình thức; mã CDC
và các phép tính lấy từ code/dịch vụ thật của GlucoGuide.

## 1. Giao diện và tiếng Việt

Ba trang được chỉnh theo bố cục xanh nhạt, thẻ nội dung, khoảng cách và trạng
thái rỗng của mẫu. Bổ sung các công cụ vào trang hiện có thay vì thay app bằng
file HTML mẫu. Dùng Segoe UI và font hệ thống hỗ trợ tiếng Việt, không tải
font từ CDN. Nhãn, dữ liệu và mã nguồn được lưu UTF-8.

Đã kiểm tra trình duyệt Edge ở desktop và chiều rộng 390 px: văn bản tiếng
Việt đúng, không tràn ngang, menu đóng đúng, input có kích thước đọc được.
Font cụ thể có thể khác theo hệ điều hành vì dùng font hệ thống.

## 2. Hỏi về BMI có số đầu vào

Ở Trợ lý kiến thức có thể hỏi:

- “BMI 59 của mik có quá cao k”.
- “BMI 30,5 có cao không, tôi 25 tuổi?”.
- Với form đủ dữ liệu và đã bật dùng hồ sơ: “BMI của mình có cao không?”.

Hệ thống nhận số có nhãn BMI, ghi nguồn gốc từ câu hỏi hoặc form, rồi đối
chiếu quy tắc từ tài liệu NIDDK mới. Khi không biết tuổi, trả lời có điều kiện
từ 20 tuổi trở lên; nhóm tuổi 18–24 trong form không được coi là đủ để khẳng
định đã từ 20 tuổi. Trẻ em, ngữ cảnh thai kỳ, nhiều giá trị hoặc số khác form
được yêu cầu làm rõ. Không tự ghi đè form hoặc kết luận tiểu đường từ BMI.

Nguồn quy tắc: `data/knowledge/clinical_rules.json`, tham chiếu `bmi.md`
và checksum của văn bản. Quy tắc mất hiệu lực nếu nguồn thay đổi. Chỉ nhận
các khoảng trong bảng đang có; số nằm giữa các ranh giới thập phân được bảng
thể hiện hoặc dưới phạm vi bảng sẽ được yêu cầu kiểm tra thêm, không làm tròn ngầm.

Hai citation trong câu trả lời BMI lấy từ bảng BMI và đoạn xét nghiệm NIDDK,
qua chính loader/chunker đang dùng. Nhánh này đọc nguồn cục bộ đã xác minh,
không gọi Gemini và không mô tả rằng Neo4j đã được truy vấn. Trace ghi
`mode=sourced_rule`, khác với `hybrid_graph` của RAG.

## 3. Thử thay đổi hồ sơ

1. Nhập đủ 21 trường ở Phân loại chỉ số và bấm Phân loại chỉ số.
2. Bấm “Thử thay đổi và giải thích điểm” ở thẻ kết quả, hoặc cuộn tới
   “Khám phá mô hình” phía dưới form.
3. Chọn trường và giá trị bản thử, rồi bấm So sánh trước–sau.
4. Đọc điểm, lớp, ngưỡng, thay đổi và chênh lệch điểm. Nút Thử BMI giảm 3
   giữ nguyên 20 trường khác và không sửa hồ sơ gốc.
5. Chỉ bấm Áp dụng bản thử vào form nếu muốn thay input. Giao diện đánh dấu
   kết quả trước là cũ; cần chạy Phân loại chỉ số lại để cập nhật.

Đây là độ nhạy của model, không phải dự đoán hiệu quả điều trị hoặc mức giảm
nguy cơ mắc bệnh. Backend từ chối bản thử sai miền hoặc mã categorical lẻ.
Frontend dùng phiên bản request và đầu vào để bỏ qua phản hồi cũ.

## 4. So sánh hai mô hình và mức ảnh hưởng

Trong Khám phá mô hình:

- **So sánh hai mô hình:** chạy MLP và Logistic Regression thật trên cùng hồ
  sơ và scaler. Giữ ngưỡng riêng: khoảng 0,6209 cho MLP và 0,5890 cho baseline
  của phiên bản hiện tại. Không cộng trung bình điểm thành tỷ lệ bệnh.
- **Ảnh hưởng 21 đặc trưng:** đọc báo cáo xáo trộn cột trên tập kiểm tra gốc.
  Đây là mức phụ thuộc chung của model, không phải đóng góp chính xác của
  từng trường trong hồ sơ hiện tại hoặc mức nguy hiểm y khoa.

`artifacts/model_manifest.json` ràng buộc baseline, MLP, scaler và metrics
bằng checksum. Khi một model lỗi, phần so sánh giữ model còn hoạt động.
Báo cáo ảnh hưởng phải khớp model version, checksum trọng số và scaler.

Khi chủ động đổi model, có thể tạo lại báo cáo ảnh hưởng bằng:

```powershell
.\.venv\Scripts\python -X utf8 -m evaluation.inspect_model
```

Lệnh này đọc CSV và tập test theo seed huấn luyện, không train lại. Chỉ dùng
để khảo sát; không điều chỉnh model theo kết quả trên test rồi coi cùng test
là đánh giá độc lập mới.

## 5. Hỏi nối tiếp trên cùng hồ sơ

Form và kết quả được giữ trong bộ nhớ tab khi đổi trang. Ở Trợ lý kiến thức,
bật “Dùng hồ sơ trong phiên cho câu hỏi này” để đưa hồ sơ đủ 21 trường tới
backend. Các đặc trưng không được đưa vào payload Gemini; model xử lý local.

Ví dụ:

1. “BMI của mình có cao không?”.
2. “Nếu giảm 3 thì sao?”.

Backend tạo bản thử BMI từ form gốc. Câu mơ hồ không có trọng tâm BMI hoặc
chưa có đủ hồ sơ sẽ yêu cầu làm rõ. Chưa triển khai trí nhớ hội thoại tự do
cho mọi loại thông số. Nhiều lần thử hiện đều dựa trên hồ sơ gốc; muốn đổi
hồ sơ gốc phải dùng thao tác Áp dụng ở trang Phân loại.

Cuộc trò chuyện mới xóa lịch sử chat và tắt việc dùng hồ sơ; form vẫn giữ
riêng trong tab. Tải lại hoặc đóng tab làm mất dữ liệu phiên. Không dùng
localStorage, SQLite hoặc database để lưu hồ sơ sức khỏe lâu dài.

## 6. Đồ thị bằng chứng và dữ liệu khảo sát

Ở cuối trang Trợ lý kiến thức, mở “Đồ thị và kiểm chứng nguồn Neo4j”, nhập
chủ đề rồi Truy xuất. Bấm quan hệ để xem điều kiện, quote và đường
`RelationFact → Evidence → Chunk → Document`. Chi tiết evidence được lọc
theo đúng relation ID, không tự gắn một đoạn khác vào cạnh.

Đây là dữ liệu Neo4j trả về và được backend đối chiếu snapshot. Mỗi lần chỉ
hiện tối đa 12 quan hệ trên màn; không xuất toàn database. Neo4j lỗi hoặc
không có đường phù hợp thì báo trạng thái thật, không dựng sơ đồ giả.

Trang Tổng quan có mục mở rộng Khám phá dữ liệu khảo sát CDC. Chọn khoảng
BMI và nhóm tuổi để đếm nhãn trong CSV đã loại trùng. Kết quả là nhãn khảo
sát, không phải nhãn model dự đoán hoặc xác suất mắc bệnh của một cá nhân.
API chỉ nhận bộ lọc cố định, không nhận SQL hay mã tự do.

## 7. API được bổ sung

| Endpoint | Chức năng | Gemini |
| --- | --- | --- |
| `POST /api/v1/scenarios` | Trước–sau trên hồ sơ gốc và thay đổi hợp lệ | Không |
| `POST /api/v1/models/compare` | MLP và Logistic Regression, ngưỡng riêng | Không |
| `GET /api/v1/model-inspection` | Báo cáo ảnh hưởng đúng artifact | Không |
| `POST /api/v1/dataset/query` | Thống kê nhãn thật theo bộ lọc | Không |
| `/chat`, `/analyze` mở rộng | Hồ sơ tùy chọn và trọng tâm BMI | Theo nhánh xử lý |

`AnalysisResponse` giữ các trường cũ, thêm `profile_hash`, `measurement_result`
và `scenario_result` tùy chọn. `/predict` và cấu trúc điểm MLP giữ nguyên.
Đồ thị tái sử dụng `/retrieve`; không kết nối Neo4j từ trình duyệt.

## 8. Dữ liệu và kết quả xác minh

Đã thêm đúng một tài liệu NIDDK, tạo 9 chunk mới. Sao chép 58 vector thật
cũ vào collection ứng viên; không embedding lại các tài liệu không đổi.

Snapshot đã kích hoạt:

- Collection: `diabetes_knowledge_20261105`.
- Snapshot: `dda7fa12276ad18120a9ceb6f119085fbeeed6370fe0fcd87be0bf70a102b644`.
- 6 tài liệu, 67 chunk, 37 thực thể, 38 phát biểu, 40 evidence.
- Neo4j migration kiểm chứng được provenance và 223 quan hệ cấu trúc.

Bộ 50 câu truy xuất cũ được giữ nguyên để đo lại:

| Cấu hình trên corpus mới | Recall@5 | MRR | nDCG@5 |
| --- | --- | --- | --- |
| Vector | 0,9667 | 0,8174 | 0,8438 |
| Vector + Neo4j | 0,9667 | 0,8507 | 0,8751 |

Corpus 58 chunk trước đó có Recall@5 0,9778 và MRR graph khoảng 0,8619.
Corpus mới có Recall giảm khoảng 1,11 điểm phần trăm trên bộ gold cũ;
không tuyên bố nâng chất lượng chung dựa vào việc thêm nguồn. Graph vẫn cải
thiện thứ hạng so với vector trên cùng corpus mới. Đây là đo truy xuất,
không chứng minh toàn bộ câu trả lời đúng nghĩa hoặc có giá trị lâm sàng.

Bằng chứng được lưu riêng, không ghi đè báo cáo lịch sử:

Các báo cáo JSON/XML kiểm chứng chính được giữ trong repository. Ảnh chụp giao
diện, ZIP sao lưu và thư mục tạo Word/PDF chỉ có ở máy làm việc, đã được gitignore.

- `artifacts/development_index_staging.json`.
- `artifacts/development_retrieval_verification.json`.
- `artifacts/development_pytest.xml`: 193 bài đạt, có 13 bài Neo4j thật.
- `artifacts/development_playwright.json`: 11 bài trình duyệt đạt.
- `artifacts/development_live_verification.json`: 2 câu kiến thức gọi Gemini
  thật; 3 ca BMI/mô phỏng local thành công và 1 yêu cầu liều thuốc bị chặn.
- `artifacts/development_upgrade_report.json`: tổng hợp thay đổi, checksum và kiểm thử.
- `artifacts/development_source_backup.zip`: bản sao các tệp trước sửa trong phạm vi
  được liệt kê ở báo cáo; không phải bản sao toàn dự án và không chứa `.env`.
- Ảnh chụp thật: `artifacts/ui_upgrade/`, không phải ảnh HTML mẫu. Bản trong
  `frontend/test-results/` có thể được thay khi chạy Playwright lần sau.

Các bài Python có cảnh báo deprecation của joblib/NumPy; không có test thất bại.
Unit test dùng Gemini mock không được tính như kết quả live.

## 9. Khởi động và khôi phục

Không cần tải, train hay index lại để mở app trên máy hiện tại. Khởi động lại
API và Vite sau khi cập nhật vì có thay đổi route, proxy và cấu hình collection.
Các lệnh chạy vẫn nằm ở đầu README. Không có dependency runtime mới.

Muốn kiểm tra reindex lặp lại đúng tài liệu BMI:

```powershell
.\.venv\Scripts\python -X utf8 -m ingestion.index_documents --document-id niddk-bmi
```

Nếu nguồn không đổi, trạng thái phải là `unchanged`, không gọi embedding thêm.

Collection `diabetes_knowledge` và snapshot cũ vẫn giữ nguyên để rollback:
`f70e5a9bc1bd55ff0e832eb266438204743f539f63ae62b0724912410f366b86`.
Dừng API trước khi đổi cấu hình rồi chạy:

```powershell
.\.venv\Scripts\python -X utf8 -m ingestion.activate_snapshot f70e5a9bc1bd55ff0e832eb266438204743f539f63ae62b0724912410f366b86
```

Đặt `CHROMA_COLLECTION=diabetes_knowledge` trong `.env`, sau đó mở lại API.
Lệnh xác minh corpus/Chroma/Neo4j trước khi đổi active; không xóa chỉ mục mới.
Rollback retrieval không tự xóa nguồn BMI hay thay đổi code quy tắc.

Playwright dùng cổng riêng 8105/5185 và key Gemini rỗng cho process test;
không dừng hoặc tái sử dụng server 8000/5173 của người dùng. Có thể đổi bằng
`PLAYWRIGHT_API_PORT` và `PLAYWRIGHT_WEB_PORT`. Vite hỗ trợ `VITE_API_TARGET`
cho proxy kiểm thử; chạy thông thường vẫn dùng API ở 8000.

## 10. Giới hạn còn lại

- Kiểm tra ý nghĩa mới chặn một số lỗi tráo khoảng xét nghiệm đã quan sát;
  chưa phải bộ chứng minh ngữ nghĩa tổng quát và chưa có người duyệt y khoa.
- Chưa thêm lượt Gemini rà soát/sửa claim tự động, SHAP từng cá nhân, SSE,
  sân khấu 3D hoặc lịch sử lưu lâu dài. Các phần này là tùy chọn giai đoạn sau.
- Hội thoại nối tiếp hiện hỗ trợ BMI và công cụ định sẵn, không phải chatbot
  tự quản lý mọi hồ sơ/thông số bằng ngôn ngữ tự nhiên.
- RAG tự do vẫn cần key/quota khi gọi Gemini; bộ kiểm tra không bảo đảm mọi
  cách hỏi đều có câu trả lời đúng. Wiki, BM25 và reranker giữ chính sách bật/tắt cũ.
- Mô hình và điểm đầu ra vẫn giữ giới hạn học thuật của dữ liệu BRFSS 2015.
