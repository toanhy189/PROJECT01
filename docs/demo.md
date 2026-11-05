# Kịch bản demo MVP

Bản giao diện/công cụ **05/11/2026** có thêm đối chiếu BMI, bản thử trước–sau,
so sánh LR/MLP, hồ sơ trong phiên và đồ thị trong React. Xem các bước thao tác
thực tế ở [development_upgrade.md](development_upgrade.md). Các số 58 chunk và
mốc 03/11 bên dưới thuộc bản demo cũ; corpus đang dùng có 67 chunk.

Đối chiếu ngày **03/11/2026**. Local đang dùng vector + Neo4j; BM25/wiki/reranker
tắt. Neo4j là đồ thị kiến thức, LangGraph là luồng điều phối các agent.

## Chuẩn bị

Chạy API và React theo README. Kiểm tra `/health`, `/api/v1/model-info` và
Swagger `/docs`. Model-info phải `ready=true` nếu có artifact đã train.
RAG live cần Gemini key trong `.env` và đã chạy `ingestion.index_documents`.
Nếu chưa có key, trình bày fallback và test mock; không gọi đó là demo RAG live.
Với Neo4j, mở Docker Desktop và chạy `scripts/run-neo4j.ps1` trước API.
Kiểm tra thêm `/api/v1/retrieval-info` và `/api/v1/graph/stats`; endpoint thứ hai
mới truy vấn database thật. Không cần train/tải/index lại nếu dữ liệu hiện có chưa đổi.

## 1. Tổng quan, khoảng một phút

Mở trang Tổng quan, giới thiệu 21 đặc trưng, Coordinator + 4 Agent, phân loại CDC
và tra cứu tài liệu NIDDK. Chỉ rõ giới hạn khảo sát, nhãn gộp, không chẩn đoán.

## 2. Phân loại mô hình thật

Mở Phân loại chỉ số. Dùng các giá trị trong `sample_request.json` để nhập minh họa,
không nhập bệnh án thật. Ví dụ Age 5 phải chọn nhóm 40–44; Sex 0 chọn Nữ;
GenHlth 2 chọn Rất tốt; Education 5, Income 6 theo nhãn UI.
Không nhập câu hỏi kèm, bấm Phân loại.

Kỳ vọng: điểm trong [0,1], predicted class theo threshold đã lưu, model version thực,
thông báo hạn chế; trace Coordinator → Prediction Agent → Safety Agent.
Không cam kết trước một score hoặc class; chúng do artifact tính ra.

Có thể gọi API từ PowerShell:

```powershell
$payload = Get-Content -LiteralPath docs/sample_request.json -Raw -Encoding UTF8
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8000/api/v1/analyze -ContentType 'application/json; charset=utf-8' -Body ([System.Text.Encoding]::UTF8.GetBytes($payload))
```

## 3. Validation

Trên Swagger gửi thiếu BMI hoặc Age=45. Kỳ vọng HTTP 422, thông báo tiếng Việt và
tên trường lỗi; không âm thầm gán mặc định. Khi bỏ model artifact ở môi trường demo
riêng rồi restart, model-info `ready=false`, `/predict` trả 503 thay vì số giả.
Không xóa model đang dùng chỉ để demo; kiểm thử tự động đã kiểm tra nhánh này.

## 4. Trợ lý kiến thức

Hỏi: “Tiểu đường là gì?”, “A1C phản ánh glucose máu trong bao lâu?”.
Nếu đã có key/index: kỳ vọng retrieval thực, draft Gemini tiếng Việt, citation ID
khớp evidence; mở từng nguồn để đối chiếu nội dung và URL.
Trace: Coordinator → Knowledge → Consultation → Safety.
Không khẳng định retrieval luôn đạt trước khi đo benchmark.

Nếu thiếu key hoặc Gemini timeout: phản hồi giới hạn, nguồn rỗng, có node lỗi thật.
Khi thiếu key, nhánh graph vẫn có thể tìm tài liệu local; bước sinh câu trả lời
Gemini vẫn lỗi, nên kết quả chat cuối cùng là fallback. Không kết luận KB rỗng
chỉ từ thông báo lỗi API.
Nếu evidence không phù hợp: không gọi LLM, Safety báo chưa đủ bằng chứng.
Đặt câu ngoài phạm vi tài liệu để kiểm tra fallback; kết quả phụ thuộc ngưỡng retrieval.

## 5. Kết hợp

Điền form 21 trường, thêm câu hỏi “Tài liệu nói gì về hoạt động thể chất và tiểu đường?”.
Kỳ vọng intent combined; trace có Prediction, Knowledge, Consultation, Safety.
Khi RAG lỗi, vẫn có prediction_result nếu mô hình đã suy luận được, nhưng phần tư vấn
báo giới hạn. Score không được diễn giải thành xác suất bệnh trong tương lai.

## 6. Safety

Hỏi “Kê thuốc giúp tôi”, “Liều dùng insulin bao nhiêu?”, “Tôi có bị tiểu đường không?”.
Kỳ vọng Coordinator chuyển thẳng Safety, không kê thuốc/chẩn đoán, không gọi Gemini.
Đây là bộ quy tắc cho MVP; không tuyên bố lọc được mọi cách diễn đạt nguy hiểm.

## 7. Kết quả và kiểm thử

Mở `artifacts/metrics.json`, so sánh MLP và Logistic Regression, giải thích precision,
recall, ROC-AUC/AP và confusion matrix. Mở `calibration.png` để giải thích giới hạn score.
Chạy pytest và Playwright theo README; không cần API Gemini trong unit test.
Với RAG, mở báo cáo chỉ sau khi đã chạy live, tách citation rule-check khỏi groundedness chấm tay.

## 8. Demo Neo4j và vai trò graph

Mở Browser **http://localhost:17474**, đăng nhập bằng tài khoản local theo `.env`.
Khai báo tham số rồi chạy từng query trong [neo4j_demo.cypher](neo4j_demo.cypher)
theo [neo4j_demo.md](neo4j_demo.md#cypher-dùng-để-demo).
Giải thích một đường đi: **phát biểu → bằng chứng → đoạn văn → tài liệu gốc**.
36 phát biểu y khoa khác với 206 cạnh dùng để nối cấu trúc dữ liệu.

Qua Swagger gọi `POST /api/v1/retrieve` với `retrieval_mode=graph` và câu r36 trong
hướng dẫn Neo4j. Mode này kết hợp vector + graph; không sinh câu trả lời LLM.
Chỉ xác nhận Neo4j đã tham gia khi trace có `backend=neo4j`, `connected=true`,
`query_count>0` và bằng chứng vào context. Câu không khớp thực thể/ý định có thể
không chạy Cypher. Endpoint này vẫn thử gọi query embedding Gemini.

Để demo không gọi Gemini lại, dùng query embedding thật đã cache:

```powershell
.\.venv\Scripts\python -X utf8 -m evaluation.demo_graph --case-id r36 --output artifacts/graph_demo_neo4j.json
```

Neo4j vẫn phải đang chạy. Khi trình bày kết quả, dùng
`artifacts/neo4j_upgrade_report.json` cho hiện trạng; `rag_upgrade_report.json` là
giai đoạn NetworkX cũ. `rag_metrics.json` là lần đo sinh câu trả lời trên **55 chunk**,
không phải corpus hiện tại **58 chunk**. Wiki chưa được nhập; không dùng fixture
giao diện làm bằng chứng đã có dữ liệu wiki thật.
