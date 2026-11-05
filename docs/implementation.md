# Nhật ký triển khai và kiểm chứng

Yêu cầu gốc được giữ trong file prompt cục bộ; file này không đưa lên GitHub.
Thư mục ban đầu chỉ có file này, không có repository Git hoặc code có sẵn.
Không đổi stack và không tạo service riêng cho Agent. Triển khai trong workspace local.
Đây là nhật ký theo thời điểm: “chưa có key”, “chưa index live” và số test trong
các phase đầu là trạng thái lịch sử. Hiện trạng mới nhất nằm ở cuối tài liệu,
[architecture.md](architecture.md) và [neo4j_demo.md](neo4j_demo.md).

## Phase 1 — Foundation

Tạo `backend/main.py`, cấu hình `.env.example`, schema, health test, React/Vite/TS/Tailwind,
README và `.gitignore`. `python -m pytest tests/test_health.py`: **1 passed**.
`npm run build`: thành công với giao diện khung. Cài dependency trong `.venv` và frontend.
Lần cài/tải đầu bị hạn chế mạng sandbox; đã dùng quyền mạng cho các lệnh cài/tải tiếp theo.

## Phase 2 — Deep Learning

Tạo `training/download_data.py`, `preprocess.py`, `eda.py`, `train.py`, `evaluate.py`,
`backend/ml/` và feature schema. CSV chính thức tải được, schema và miền mã đã kiểm tra.
`python -m pytest tests/test_preprocessing.py`: **10 passed**.
`python -X utf8 -m training.eda`: thành công; cần UTF-8 khi in tiếng Việt trên Windows.
`python -X utf8 -m training.train`: **thành công**, 17 epoch, metrics thật lưu trong artifacts.
Kết quả chi tiết trong evaluation.md. Có kiểm thử tích hợp nạp artifact thật và gọi HTTP.

## Phase 3 — RAG indexing

Tạo loader PDF/Markdown, cleaner, chunker, embedding service, Chroma store,
download/index CLI và manifest 5 tài liệu NIDDK. `ingestion.download_sources` đã chạy,
5/5 nguồn tải được; checksum nằm trong download_report.json.
Unit test kiểm tra PDF thật tạo trong test, Markdown, chunk/metadata, Gemini mock,
ChromaDB thật, re-index lặp và đổi model/dimension. Chưa index Gemini live vì thiếu key.

## Phase 4 — Retrieval

Tạo retriever, context builder, Gemini provider trả structured claims và citation validator.
Kiểm thử task query/document, L2 normalization, timeout, context budget, duplicate,
ID/quote/số liệu không được hỗ trợ. Các kiểm thử nằm trong `tests/test_rag.py`.
Chưa xác minh API Gemini live; tài liệu và mã tích hợp đã có.

## Phase 5 — Multi-Agent và API

Tạo AgentState, Coordinator, 4 Agent, LangGraph routing, wrapper trace thực,
API model-info/predict/chat/analyze và lỗi 422/503/500. Unit/integration tests
bao phủ prediction/knowledge/combined, missing input, empty evidence, Gemini lỗi,
citation sai, nội dung không an toàn. Lệnh pytest toàn bộ ban đầu: **29 passed**.

## Phase 6 — React integration

Tạo dashboard GlucoGuide, form đủ 21 trường có mapping Age/GenHlth/Education/Income,
chat với citations, Agent Trace, responsive layout và loading/error states.
`npm run build`: thành công. `npx playwright test`: **3 passed** trên Edge headless;
gọi model thật qua UI, kiểm tra fallback không có key, menu/mobile không tràn ngang.
Ảnh kiểm tra tại `frontend/test-results/`; đã mở ảnh để kiểm tra giao diện.

## Phase 7 — Evaluation và demo

Tạo 10 câu RAG có reference quote thực từ corpus, evaluator Recall@K/MRR/citation rule-check,
latency và cơ chế chấm groundedness thủ công. Tạo README, kiến trúc Mermaid, data dictionary,
báo cáo đánh giá, sample request, demo, script PowerShell và khóa phiên bản đã kiểm thử.
Pytest sau bổ sung kiểm tra liều, đơn vị xét nghiệm, embedding lỗi và artifact hỏng:
**46 passed**, 6 cảnh báo deprecation joblib/NumPy, không có test skip trong môi trường này.
`pip check`: không có dependency hỏng. `compileall`: exit 0.
Định dạng Python bằng Ruff, React/TypeScript/CSS bằng Prettier; kiểm tra lỗi tĩnh
Python không phát hiện lỗi. Script PowerShell đã kiểm tra cú pháp.
Lệnh index và evaluate RAG đã thử chạy thực tế, dừng có chủ đích với exit 1 và
thông báo thiếu GEMINI_API_KEY; không tạo metrics/chỉ mục giả.

## Cập nhật sau khi người dùng cấu hình Gemini key

Người dùng đã index 5/5 tài liệu, 55 chunks bằng Gemini thật, không có lỗi.
Lần đánh giá đầu lỗi trước khi gọi LLM do `response_schema` của SDK không hỗ trợ
`additionalProperties`. Đã chuyển sang `response_json_schema`, giữ kiểm tra Pydantic.
Thêm kiểm thử dùng bộ serialize SDK thật với HTTP mock để bắt hồi quy này.

Model `gemini-3.8-flash` xuất hiện trong danh sách tài khoản nhưng trả 504, kể cả
yêu cầu ngắn. Đã kiểm tra được một câu RAG thật bằng `gemini-2.5-flash` và chuyển
cấu hình local sang model này. Embedding và chỉ mục được giữ nguyên.
Evaluator giữ Recall@K/MRR khi bước truy xuất thành công dù LLM bị lỗi; lưu thêm
mã lỗi an toàn và evidence của các câu thất bại. Bộ Pytest hiện đạt **57 passed**.
Kết quả đánh giá live giai đoạn này nằm trong `artifacts/rag_metrics.json`;
retrieval hoàn tất 10/10 câu, Recall@5 = 1,0 và MRR = 0,866667. Toàn pipeline hoàn tất
9/10: 8 passed, 1 fallback, 1 lỗi 429. Citation rule-check 23/24 claims; groundedness
ngữ nghĩa vẫn cần người chấm. Đã thêm pacing giữa câu, cấu hình thinking phù hợp
với Flash 2.5 và kiểm thử tránh nhầm số chỉ típ bệnh với số liệu y khoa.
Không có hosting public hoặc bệnh án thật.

## Hoàn thiện ingestion — 01/11/2026

Bổ sung DOCX/TXT, giữ thứ tự paragraph/bảng và heading lồng nhau, sửa parser NIDDK
làm mất tham khảo/chú thích hoặc sai cấp heading. PDF trang rỗng text được báo rõ,
chưa triển khai OCR/ảnh/DOC cũ. Giữ Custom Chunking, bổ sung kiểm tra offline và bỏ
qua tài liệu không đổi. Đợt này đạt **84 test**, cập nhật corpus từ 55 lên **58 chunk**
bằng Gemini thật, lần chạy tiếp không gọi embedding. Chi tiết: [ingestion.md](ingestion.md).

## Hybrid, graph, wiki và reranker — giai đoạn NetworkX 03/11/2026

Tạo snapshot bất biến, BM25/RRF, graph có evidence nguồn và adapter wiki khóa revision.
Thử retrieval trên 50 câu, giữ baseline corpus/vector. Ở giai đoạn này graph/BM25
làm giảm Recall nên giữ tắt; reranker CPU cũng không qua kiểm định chất lượng/độ trễ.
Wiki thật bị HTTP 403, không nhập nguồn giả. Đã chạy **125 test Python**, **5 test
Playwright** và build. Báo cáo giai đoạn: [rag_upgrade.md](rag_upgrade.md).

## Migration Neo4j và đổi cách hợp nhất — 03/11/2026

Thêm Neo4j Community làm backend graph chính, giữ NetworkX để đối chiếu/rollback.
Database thật có 36 Entity, 36 RelationFact, 38 Evidence, 58 Chunk và 5 Document
trong snapshot active. Migration lặp an toàn, giữ nguyên vector, kết quả RRF khớp
200/200 danh sách cũ. `vector_guarded` giữ tập top-k vector để tránh mất bằng chứng;
local bật vector + Neo4j, BM25/wiki/reranker tắt. MRR tăng trong bộ thử thăm dò;
chưa có đánh giá mù/chuyên gia hoặc đo lại chất lượng sinh câu trả lời.
Đạt **150 test**, gồm **13 test Neo4j thật**. Chi tiết: [neo4j_demo.md](neo4j_demo.md).

## Dọn dự án và rà soát tài liệu — 03/11/2026

Đã dọn cache/tệp build và hai báo cáo trùng, khoảng 498 MB; giữ code, dữ liệu,
artifact mô hình, Chroma, Neo4j, snapshot và bằng chứng baseline. Cache reranker
đang tắt được dọn; muốn dùng lại cần tải lại bằng benchmark `--download`.
Lần dọn chạy lại **150 test Python**, build frontend, Ruff và pip check; không
chạy lại Playwright/Gemini generation. Báo cáo: `artifacts/cleanup_report.json`.

Đã đối chiếu README và 8 tài liệu Markdown trong `docs/` cùng sample JSON/Cypher
với code/cấu hình/báo cáo; cập nhật sơ đồ Neo4j, API retrieval, hướng dẫn cập nhật
index và tách số liệu lịch sử khỏi hiện tại. Rà soát tài liệu không thay code ứng
dụng, model, corpus, vector hoặc cờ `.env`.

## Công cụ mô hình và giao diện mới — 05/11/2026

Đã triển khai phần ưu tiên của kế hoạch: đối chiếu BMI có nguồn NIDDK, thử thay đổi
đặc trưng trên bản sao hồ sơ, so sánh MLP với Logistic Regression, xem ảnh hưởng
21 đặc trưng và thống kê dữ liệu khảo sát. Form và hội thoại giữ trong bộ nhớ tab;
người dùng chủ động cho phép dùng hồ sơ khi hỏi tiếp. Không huấn luyện lại hay đổi
trọng số, scaler và ngưỡng phân loại.

Giao diện tham khảo ZIP người dùng cung cấp, giữ đúng mã hóa 21 đặc trưng gốc.
Dùng font hệ thống hỗ trợ tiếng Việt; đã kiểm tra màn hình máy tính và điện thoại.
Đồ thị hiển thị quan hệ và bằng chứng thật từ Neo4j qua API hiện có.

Thêm một tài liệu BMI với 9 chunk; giữ 58 vector cũ trong collection mới, kiểm chứng
Neo4j trước khi kích hoạt. Hiện có **6 tài liệu, 67 chunk, 37 Entity, 38 RelationFact
và 40 Evidence**. Collection/snapshot cũ được giữ để khôi phục. Recall@5 trên bộ
gold cũ giảm khoảng 1,11 điểm phần trăm khi thêm nguồn; graph cải thiện thứ hạng
so với vector trên cùng corpus mới. Không coi phép đo này là đánh giá y khoa.

Kiểm thử cuối đạt **193 bài Python**, gồm **13 bài Neo4j thật**, **11 bài Playwright**,
build frontend và Ruff. Đã thử hai câu kiến thức qua Gemini thật; các ca BMI và
mô phỏng dùng công cụ local, không giả lập kết quả API. Chạy lại phép đo ảnh hưởng
đặc trưng cho kết quả trùng khớp báo cáo đã lưu.

Chi tiết cách dùng và giới hạn: [development_upgrade.md](development_upgrade.md).
Bằng chứng máy đọc: `artifacts/development_upgrade_report.json`. SHAP từng hồ sơ,
SSE, giao diện 3D và lưu lịch sử lâu dài vẫn là tùy chọn giai đoạn sau.
