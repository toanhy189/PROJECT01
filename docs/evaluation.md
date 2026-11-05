# Báo cáo đánh giá thực tế

Cập nhật **05/11/2026**: corpus 6 nguồn/67 chunk; 193 test Python gồm 13 Neo4j
thật; 11 Playwright; build và Ruff đạt. Vector và vector + graph cùng Recall@5
0,9667; MRR lần lượt 0,8174 và 0,8507. Recall giảm nhẹ so với corpus 58 chunk.
Hai câu RAG gọi Gemini thật và các công cụ local đã kiểm tra riêng, chưa phải
đánh giá sinh câu trả lời trên toàn bộ benchmark. Chi tiết, artifact và giới hạn:
[development_upgrade.md](development_upgrade.md). Các mục có ngày cũ dưới đây
giữ nguyên làm lịch sử, không phải số đo của corpus mới.

Huấn luyện và đánh giá RAG ban đầu: **01/11/2026**, múi giờ Asia/Bangkok.
Retrieval/Neo4j và kiểm tra gần nhất: **03/11/2026**. Tài liệu đã đối chiếu lại
code và báo cáo ngày 03/11. Metrics mô hình thuộc một lần huấn luyện seed 42,
không phải khoảng tin cậy hay đánh giá lâm sàng.

Trạng thái local hiện tại là **vector + Neo4j, fusion `vector_guarded`**, BM25,
wiki và reranker tắt. Phần NetworkX/RRF bên dưới được giữ làm kết quả lịch sử.

## Dữ liệu và chống rò rỉ

- Nguồn: [UCI CDC Diabetes Health Indicators](https://archive.ics.uci.edu/dataset/891/cdc+diabetes+health+indicators), DOI `10.24432/C53919`.
- CSV tải từ `https://archive.ics.uci.edu/static/public/891/data.csv` qua API metadata UCI.
- SHA-256: `9f71fda9d4ae5f4878c99b9233b6a16accfa9a17c194116a6b78100540934964`.
- 253.680 hàng; 21 đặc trưng, một target `Diabetes_binary`; không missing.
- Nhãn gốc: 0 = 218.334 hàng, 1 = 35.346 hàng, khoảng 13,93% lớp 1.
- 24.206 hàng trùng hoàn toàn được loại; còn 229.474 hàng.
- Min/max và kiểu dữ liệu từng cột đã đọc thật, lưu tại `artifacts/data_report.json`.
- Train: 160.636 hàng; validation: 34.427; test: 34.411.
- Tỷ lệ lớp 1 sau chia khoảng 15,29% / 15,29% / 15,30%.

Nhóm cùng 21 đặc trưng được giữ trong một tập, kể cả khi nhãn khác nhau.
Train/validation/test chia stratified ở mức nhóm theo nhãn lớn nhất trong nhóm.
StandardScaler fit trên train; class weights tính từ train. Test không tham gia fit,
early stopping hoặc chọn ngưỡng. Việc loại duplicate làm thay đổi phân bố so với
dataset gốc, nên không so trực tiếp metrics với nghiên cứu dùng split khác.

## Cấu hình và metrics test

Model version: `cdc-mlp-20261101T102617Z`. Python 3.13.5; PyTorch 2.15.0+cpu;
Scikit-learn 1.7.2. MLP `21 → 64 → ReLU → Dropout(0,2) → 32 → ReLU → 1`.
BCEWithLogitsLoss với pos_weight; Adam lr 0,001; batch 512; tối đa 30 epoch;
early stopping patience 5, chạy 17 epoch, dùng checkpoint có validation loss tốt nhất.
Ngưỡng cho từng model được chọn theo F1 cao nhất trên validation.

| Chỉ số test | Logistic Regression | PyTorch MLP |
| --- | ---: | ---: |
| Ngưỡng từ validation | 0,589020 | 0,620890 |
| Accuracy | 0,770509 | 0,780913 |
| Precision lớp 1 | 0,360976 | 0,373947 |
| Recall lớp 1 | 0,649003 | 0,640646 |
| F1 lớp 1 | 0,463920 | 0,472244 |
| ROC-AUC | 0,808013 | 0,814657 |
| PR-AUC (Average Precision) | 0,409277 | 0,434141 |
| Brier score, thấp hơn tốt hơn | 0,183628 | 0,183694 |

Confusion matrix theo thứ tự `[[TN, FP], [FN, TP]]`:

| Model | TN | FP | FN | TP |
| --- | ---: | ---: | ---: | ---: |
| Logistic Regression | 23.097 | 6.049 | 1.848 | 3.417 |
| MLP | 23.499 | 5.647 | 1.892 | 3.373 |

MLP cải thiện ROC-AUC/AP/F1 trong lần chạy này nhưng recall thấp hơn baseline một chút.
Precision còn thấp, dương tính giả nhiều. Brier khoảng 0,184 và biểu đồ calibration
cho thấy score chưa được hiệu chuẩn; class weighting ảnh hưởng phân bố score.
Không diễn giải score như xác suất mắc bệnh hoặc dự đoán tương lai.

Kết quả gốc: `artifacts/metrics.json`, `artifacts/training_config.json`.
Biểu đồ: `feature_distributions.png`, `target_distribution.png`, `calibration.png`.
Chưa làm external validation, phân tích fairness theo nhóm hoặc nhiều seed.

## Đánh giá RAG

Corpus đầu tiên dùng để đo metrics RAG bên dưới có 5 bài NIDDK thật, **55 chunks**.
Sau cải thiện ingestion, đã cập nhật thành **58 chunks** bằng Gemini thật, giữ nguyên
collection và kiểm tra chạy lặp không gọi thêm API. Chưa đo lại benchmark sinh câu trả lời
trên corpus mới; không gán metrics cũ cho corpus mới. Riêng ngày 03/11/2026 đã đo
retrieval-only trên 50 câu của corpus 58 chunk, xem phần nâng cấp bên dưới.
Chi tiết: [ingestion.md](ingestion.md), `artifacts/ingestion_quality.json` và
`artifacts/ingestion_reindex_report.json`.

Tập 10 câu tại `evaluation/rag_questions.json` chứa
question tiếng Việt, document ID, reference quote nguyên văn và đáp án tham chiếu.
Loader đánh giá xác nhận mọi reference quote tồn tại trong chunks của nguồn đó.

| Hạng mục | Trạng thái |
| --- | --- |
| PDF/DOCX/TXT/Markdown loader, cleaning, heading/câu/bảng chunking | Đã test, gồm encoding và PDF thiếu text |
| Gemini SDK, task type, normalization, timeout | Đã test bằng mock; kiểm thử serialize SDK thật với HTTP mock |
| Chroma PersistentClient, metadata, re-index và retrieval | Đã test Chroma thật, gồm retrieval live với Gemini embedding |
| Gemini embedding/indexing thật | **Đã cập nhật 5 tài liệu, 58 chunks; không lỗi; chạy lại 0 request** |
| Retrieval semantic Recall@5 và MRR | **1,0 và 0,866667 trên 10/10 câu truy xuất thành công** |
| Citation correctness đầu ra Gemini | **23/24 claims qua rule-check, khoảng 0,958333** |
| Groundedness ngữ nghĩa | **Chưa có người chấm** |
| Latency retrieval + Gemini | **Trung bình 4.618,46 ms; p95 6.762,83 ms**, không tính khoảng nghỉ |

Các chỉ số Recall/MRR, citation và latency trong bảng là lần đo **corpus 55 chunk**.
Dòng cập nhật 58 chunk chỉ xác nhận ingestion/indexing; không phải đo lại chất lượng
sinh câu trả lời trên corpus hiện tại. Phép đo 50 câu cuối tài liệu chỉ đo truy xuất.

Báo cáo live giai đoạn này: `artifacts/rag_metrics.json`. Bản sao trùng nội dung
`rag_metrics_verified.json` đã được dọn; chỉ giữ một bản kết quả. Model sinh
`gemini-2.5-flash`, embedding `gemini-embedding-001`.
Trạng thái tổng thể vẫn **incomplete**: 9/10 câu hoàn tất pipeline, trong đó 8 câu
được Safety cho qua và 1 câu fallback do trích dẫn; câu q08 bị giới hạn API 429.
Vì vậy không gọi đây là bộ đánh giá end-to-end hoàn tất hoặc đạt toàn bộ câu hỏi.
Chỉ số citation tính trên các claim của 9 câu không lỗi dịch vụ, không đại diện câu q08.

Trước đó `gemini-3.8-flash` trả 504 kể cả với yêu cầu ngắn. Lỗi schema cũ
`additionalProperties is not supported in the Gemini API` đã được sửa bằng
`response_json_schema`. Báo cáo lỗi ban đầu được giữ ở `artifacts/rag_metrics_before_fix.json`;
lần thử ngay sau sửa schema được giữ ở `artifacts/rag_metrics_schema_fix.json`.
Lần chạy cuối nghỉ 7 giây giữa các câu, nhưng vẫn có 429; có thể tăng thời gian nghỉ
hoặc kiểm tra quota/token của tài khoản trước khi đánh giá lại.

Không gán kết quả retrieval với vector mock thành chất lượng tìm kiếm y khoa.
Không tạo metrics giả để điền các ô chưa đo.

Khi đã cấu hình key và index:

```powershell
.\.venv\Scripts\python -X utf8 -m ingestion.index_documents
.\.venv\Scripts\python -X utf8 -m evaluation.evaluate_rag --output artifacts/rag_metrics_current.json
```

Script mặc định ghi đè `artifacts/rag_metrics.json`; lệnh trên chọn tên mới để giữ
báo cáo lịch sử. Kết quả mới dùng cấu hình retrieval từ `.env` lúc chạy. Script
gọi Retriever → LLM → Safety trực tiếp; không đo toàn bộ HTTP, UI hay Coordinator
LangGraph, nên “pipeline hoàn tất” ở đây chỉ nói về pipeline đánh giá RAG đó.
Gold relevant chunks là các chunk cùng document chứa reference quote:

- Recall@K = số relevant chunk được tìm thấy / tổng relevant chunks.
- MRR = trung bình nghịch đảo thứ hạng chunk relevant đầu tiên, bằng 0 nếu không tìm thấy.
- Recall/MRR lấy từ các câu truy xuất thành công, kể cả khi LLM ở bước sau bị lỗi.
- `citation_correctness_rule_check` = tỷ lệ claim qua kiểm tra ID, quote nguyên văn và số liệu.
- Latency đo thực bằng perf_counter, có mean và p95; lỗi được ghi riêng và trạng thái `incomplete`.
- `groundedness_human` mặc định null; kiểm tra ID/quote không chứng minh nhận định được nguồn hỗ trợ về nghĩa.

Để chấm groundedness, người đọc mở từng `results[].claims` và `retrieved_sources`.
Đánh giá mỗi claim tiếng Việt có được nguồn dẫn hỗ trợ đầy đủ hay không, gồm số liệu,
đối tượng, mức độ khẳng định và hướng dẫn điều trị. Lưu file JSON do người đánh giá lập:

```json
[
  {
    "case_id": "q01",
    "supported_claims": [true],
    "reviewer": "Tên người đánh giá",
    "notes": "Đối chiếu từng nhận định với nguồn trong kết quả chạy."
  }
]
```

Đây là **mẫu định dạng**, không phải kết quả đã chấm; số bool phải khớp số claims thật.
Chấm kết quả đã chạy mà không gọi Gemini lại:

```powershell
.\.venv\Scripts\python -X utf8 -m evaluation.evaluate_rag --rate-existing artifacts/rag_metrics.json --ratings ratings.json --output artifacts/rag_metrics_reviewed.json
```

Groundedness = số claim người chấm xác nhận hỗ trợ / tổng claim đã chấm; báo rõ số case/claim
đã chấm. Tập 10 câu là smoke benchmark nhỏ, chưa đủ kết luận tổng quát. Nguồn cũ cần
kiểm tra lại thời điểm và phạm vi áp dụng; không mặc định mọi thông tin còn cập nhật.

## Kiểm thử đã thực sự chạy, đối chiếu ngày 03/11/2026

| Lệnh | Kết quả |
| --- | --- |
| Pytest với `NEO4J_INTEGRATION=1`, có JUnit XML | 150 passed, gồm 13 test Neo4j thật; 6 DeprecationWarning từ joblib/NumPy |
| Compileall trên backend/training/ingestion/evaluation/tests | Đã đạt ở đợt triển khai trước; không chạy lại khi chỉ sửa tài liệu |
| `.venv\Scripts\python -m pip check` | No broken requirements found |
| Ruff trên backend/training/ingestion/evaluation/tests | All checks passed ở lần dọn dự án |
| `npm run build` trong frontend | TypeScript + Vite build thành công |
| `npx playwright test` trong frontend | 5 passed ở đợt nâng cấp; không chạy lại trong lần dọn dự án hoặc rà soát tài liệu |

Số 125 test thuộc giai đoạn NetworkX trước Neo4j. Kết quả gần nhất có trong
`artifacts/neo4j_test_results.xml` và `artifacts/cleanup_report.json`.
Lệnh `pytest` không đặt `NEO4J_INTEGRATION=1` sẽ skip 13 test database thật; không
coi đó là xác nhận kết nối Neo4j. Cách chạy: [neo4j_demo.md](neo4j_demo.md#kiểm-thử-và-tái-lập).

Pytest kiểm tra strict schema, input thiếu/thừa, mã sai/NaN, fit scaler, chia nhóm không
rò rỉ, loader PDF/DOCX/TXT/Markdown, chunk boundaries, L2/task embedding, lỗi timeout, idempotence
Chroma, retrieval metadata, context budget, citation giả, routing/safety/fallback,
HTTP status, request ID và suy luận từ artifact CDC thật.
Test ingestion còn kiểm tra thứ tự paragraph/bảng, heading kế thừa/lồng nhau, nội dung
lặp có ý nghĩa, giữ chú thích bảng, loại mục lục có điều kiện và bỏ qua tài liệu không đổi.

Playwright nhập đủ 21 trường, đối chiếu điểm UI với response từ model thật; kiểm tra chat
fallback không có nguồn giả; menu và độ rộng mobile 390px. Ảnh sinh trong
`frontend/test-results/` khi chạy test; thư mục đã được dọn, không phải artifact
đang có sẵn. Kiểm thử này không thay thế đánh giá RAG live hoặc kiểm tra y khoa.

## Kết quả giai đoạn NetworkX/RRF ngày 03/11/2026

Đã giữ snapshot 58 chunk NIDDK cùng vector thật. Bộ 50 câu đóng băng có 45 câu
answerable và 5 câu không có gold/ngoài phạm vi; query embedding Gemini thật được
cache bằng 4 batch. Các lần so sánh sau không gọi thêm embedding hoặc LLM generation.

| Cấu hình cùng corpus | Recall@5 | MRR | nDCG@5 |
| --- | ---: | ---: | ---: |
| Vector-only | 0,9778 | 0,8341 | 0,8617 |
| Vector + BM25 | 0,8667 | 0,7322 | 0,7512 |
| Vector + graph | 0,9333 | 0,8500 | 0,8722 |
| Vector + BM25 + graph | 0,8667 | 0,7711 | 0,7924 |

Graph cải thiện thứ hạng ở 4 câu, suy giảm ở 3 câu; không bổ sung gold evidence mới
ngoài top-5 baseline trên bộ này. Vì Recall tổng giảm, **ở giai đoạn này** chưa bật
graph mặc định. Sau migration và đổi fusion, local đã bật graph như phần tiếp theo.
BM25 vẫn tắt. Các tính năng đã triển khai, có API demo và công tắc thử nghiệm.
Đây là kết quả thăm dò từ gold do agent đối chiếu nguồn; phần heldout không phải
test mù độc lập vì agent đã xem báo cáo khi sửa. Chưa đo groundedness/citation mới
hoặc relation precision do người chấm. Các phép đo latency này dùng query cache,
không phải latency chat end-to-end.

Reranker multilingual đã chạy đủ 50 câu thật trên CPU: RSS parent + worker đỉnh
khoảng 1,04 GiB, warm p95 5,6 giây; heldout Recall/MRR thấp hơn RRF. Không qua gate,
giữ tắt. Wiki adapter đã test nhưng API thật trả 403 robot policy, chưa có corpus
NIDDK + wiki và chưa đo vòng B. Không sử dụng nguồn/revision mock như dữ liệu thật.

Đầy đủ nguồn, snapshot, hạn chế và lệnh tái lập: [rag_upgrade.md](rag_upgrade.md).
Các báo cáo: `artifacts/retrieval_ablation_niddk.json`,
`artifacts/reranker_benchmark.json`, `artifacts/rag_upgrade_report.json`.

## Neo4j và fusion bảo vệ vector — 03/11/2026

Các số trong phần NetworkX phía trên là kết quả trước migration. Neo4j Community
2026.10.1/driver 6.4.0 đã import đúng 36 entity/36 fact/38 evidence/58 chunk/5 tài
liệu. Migration lặp không trùng; Neo4j và NetworkX khớp 200/200 danh sách kết quả
của ablation cũ. Giữ nguyên byte float32 của vector baseline, không gọi embedding lại.

Fusion `vector_guarded` sửa lỗi mất evidence do RRF đẩy chunk ra khỏi top-5:
giữ tập vector, sắp xếp theo RRF trong tập và bổ sung nguồn ngoài khi vector chưa đủ.
Vector + Neo4j đạt Recall@5 **0,9778**, MRR **0,8619**, nDCG@5 **0,8919**; vector
baseline tương ứng **0,9778 / 0,8341 / 0,8617**. Development và heldout đều không
giảm Recall/MRR tổng hợp, nên bật graph trong cấu hình local; không phải chấp thuận
để dùng lâm sàng. R21/r24 vẫn giảm thứ hạng; chưa có gold evidence ngoài top-5 vector.
BM25 thêm vào làm MRR giảm nên chưa bật. Không đo lại reranker A4 sau gate thất bại.

Đã chạy 150 test Python, gồm 13 integration test Neo4j thật; 5 Playwright, build
frontend, Ruff và pip check trong các đợt nêu ở bảng kiểm thử; không phải tất cả
đều được chạy lại cùng một lần. Wiki vẫn chưa import do 403; chưa có groundedness hoặc
citation correctness mới. Gold do agent gán và đã xem khi tối ưu, không độc lập/mù.
Tái lập, giới hạn và báo cáo: [neo4j_demo.md](neo4j_demo.md),
`artifacts/neo4j_upgrade_report.json`, `artifacts/neo4j_test_results.xml`.

Recall/MRR/nDCG trong bộ 50 câu được tính trên **45 câu có gold**; 5 câu còn lại
không tham gia trung bình các chỉ số này. Việc truy xuất được chunk cho 5 câu đó
không chứng minh hệ thống từ chối đúng; cần đánh giá sinh câu trả lời/Safety riêng.

## Hạn chế khoa học và sử dụng

Dữ liệu khảo sát BRFSS tự báo cáo tại Hoa Kỳ năm 2015, không đại diện mọi dân số;
chưa kiểm định tại Việt Nam. Nhãn gộp không phân biệt tiền tiểu đường với tiểu đường,
không chứa thời gian theo dõi tương lai. Không suy diễn quan hệ nhân quả.
Model không dùng xét nghiệm máu để chẩn đoán. Safety rule và prompt có thể bị vượt qua;
quote validator không phát hiện hết claim sai nghĩa. Không triển khai cho chăm sóc y tế thực tế.
