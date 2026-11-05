# GlucoGuide — Diabetes Multi-Agent

MVP đồ án đại học: phân loại **21 đặc trưng khảo sát CDC** bằng PyTorch và tra cứu
kiến thức tiểu đường bằng **Custom RAG + Gemini**, điều phối bằng **LangGraph**.
Giao diện và tài liệu tiếng Việt. Chạy local trên Windows, CPU, không cần GPU.

**Không dùng để chẩn đoán, dự đoán nguy cơ mắc bệnh trong tương lai hoặc kê thuốc.**
Lớp 1 gộp tiền tiểu đường và tiểu đường theo định nghĩa nhãn dữ liệu. Điểm mô hình
chưa được hiệu chuẩn để dùng như xác suất y khoa. MVP không lưu thông tin sức khỏe nhập từ UI.

## Chạy nhanh trên máy hiện tại

**Không cần chạy hết mọi lệnh trong README mỗi lần mở app.** Đã đối chiếu ngày
**05/11/2026**: máy hiện tại có `.venv`, thư viện frontend, model đã train,
ChromaDB, snapshot và cấu hình key. Việc đã điền key không bảo đảm API còn quota.
Các lệnh tải dữ liệu, train, index và đánh giá ở phía dưới chỉ chạy khi cần chuẩn bị
hoặc cập nhật dữ liệu; chúng không phải bước mở app hằng ngày.

1. Mở **Docker Desktop**, chờ Docker Engine sẵn sàng.
2. Mở PowerShell thứ nhất, chạy:

```powershell
Set-Location -LiteralPath 'D:\NAM 4\KI I\PTHTTM\diabetes agent'
powershell -ExecutionPolicy Bypass -File scripts/run-neo4j.ps1
powershell -ExecutionPolicy Bypass -File scripts/run-api.ps1
```

Chỉ chạy dòng API sau khi lệnh Neo4j thành công; giữ cửa sổ API đang mở.
Script Neo4j kiểm chứng/import snapshot hiện có, không tạo lại embedding.

3. Mở PowerShell thứ hai, chạy:

```powershell
Set-Location -LiteralPath 'D:\NAM 4\KI I\PTHTTM\diabetes agent'
powershell -ExecutionPolicy Bypass -File scripts/run-web.ps1
```

4. Mở **http://127.0.0.1:5173**. Nếu chuyển dự án sang thư mục khác, sửa đường dẫn
ở hai khối lệnh trên. `Ctrl+C` dừng API/giao diện trong terminal tương ứng; đóng
trình duyệt không tự dừng server. Muốn dừng riêng Neo4j mà vẫn giữ dữ liệu:

```powershell
docker compose -f compose.neo4j.yml stop neo4j
```

Khi cần cài mới hoặc thiếu dữ liệu, đọc mục 1, 3, 4 và phần tạo snapshot lần đầu
trong mục 2. Các bước kiểm tra app đã chạy đủ nằm ở cuối mục 2.

## Trạng thái thực tế

### Khi clone từ GitHub

```powershell
git clone https://github.com/toanhy189/PROJECT01.git
Set-Location -LiteralPath PROJECT01
powershell -ExecutionPolicy Bypass -File scripts/setup.ps1
```

Repository giữ mã nguồn, kiểm thử, tài liệu, nguồn NIDDK và bộ model đã huấn luyện
nhỏ trong `artifacts/`. `.env`, CSV gốc, ChromaDB, thư viện đã cài, file prompt và
toàn bộ `reports/` chỉ lưu trên máy, không được đưa lên GitHub. Snapshot JSON được
giữ để đối chiếu; chúng không thay thế vector Chroma hoặc database Neo4j.

Sau khi setup, tự điền key trong `.env`; tải CSV theo mục 3 nếu cần thống kê CDC,
chạy lại phép đo hoặc các test đọc dữ liệu thật. Model đã có nên không cần train
lại để dùng chức năng phân loại. Chuẩn bị ChromaDB và Neo4j theo mục **Máy mới
chưa có ChromaDB hoặc snapshot** trước khi dùng đầy đủ RAG. Dùng đường dẫn thư mục
vừa clone, không sao chép đường dẫn ổ D của máy hiện tại ở phần chạy nhanh.

Joblib và trọng số chỉ nên nạp từ phiên bản dự án tin cậy. Không chia sẻ API key
hoặc mật khẩu khi sửa cấu hình; `.env.example` là tệp mẫu được công khai.

**Bản cập nhật 05/11/2026:** đã bổ sung đối chiếu BMI có nguồn, công cụ thử thay
đổi hồ sơ, so sánh Logistic Regression/MLP, báo cáo ảnh hưởng 21 đặc trưng,
hỏi nối tiếp BMI trên hồ sơ trong phiên, đồ thị Neo4j trong giao diện và thống
kê CDC. Giao diện tham khảo bộ redesign, dùng font hệ thống hỗ trợ tiếng Việt.
Hướng dẫn sử dụng và giới hạn: [docs/development_upgrade.md](docs/development_upgrade.md).

Kho đang dùng có **6 tài liệu, 67 chunk, 37 thực thể, 38 phát biểu và 40 evidence**.
Collection hiện tại: `diabetes_knowledge_20261105`; collection cũ giữ nguyên để
khôi phục. Chỉ 9 chunk BMI mới cần embedding. Model và ngưỡng không thay đổi.
Đã chạy 193 test Python (13 Neo4j thật), 11 test trình duyệt; build và Ruff đạt.
Số đo corpus mới: Recall@5 0,9667; MRR vector 0,8174, vector + graph 0,8507.
Recall giảm nhẹ so với corpus cũ; không coi thêm tài liệu là đã cải thiện mọi chỉ số.

Các dòng dưới đây mô tả **mốc trước bản cập nhật** để giữ nguồn gốc báo cáo cũ:

Đối chiếu hướng dẫn chạy với code/cấu hình ngày **05/11/2026**; số đo retrieval
thuộc ngày 03/11 và lần kiểm thử/demo gần nhất thuộc ngày 04/11.
`.env` là cấu hình
của máy hiện tại; `.env.example` là mẫu cho máy mới, nên trạng thái bật/tắt có thể khác.

- Đã tải CSV thật từ UCI: 253.680 hàng, 21 đặc trưng; đã kiểm tra schema và miền mã.
- Đã train Logistic Regression và MLP trên CPU, lưu artifact thật trong `artifacts/`.
- Đã tải 5 bài NIDDK, ghi URL, checksum và thời điểm tải trong `data/knowledge/`.
- Đã kiểm thử ChromaDB thật với embedding mock; toàn bộ API Gemini trong unit test dùng mock.
- Đã cải thiện ingestion và cập nhật bằng Gemini thật: 5 tài liệu, 58 chunks trong ChromaDB.
- Chạy index lại: bỏ qua cả 5 tài liệu không đổi, không gọi embedding thêm.
- Đã sửa lỗi serialize JSON schema của SDK; kết quả chạy live ghi trong báo cáo RAG ở `artifacts/`.
- Lần đánh giá RAG live trên corpus cũ 55 chunk: retrieval 10/10; pipeline 9/10
  (8 passed, 1 fallback, 1 lỗi 429). Chưa đo lại metrics này trên corpus mới 58 chunk.
- Kết quả đo và phạm vi xác minh: [docs/evaluation.md](docs/evaluation.md).
- GraphRAG dùng **Neo4j Community 2026.10.1** và driver 6.4.0, đã migration/truy vấn
  database thật: 36 thực thể, 36 phát biểu, 38 evidence, 5 tài liệu, 58 chunk.
- Cấu hình local đã chọn vector + Neo4j với `vector_guarded`: giữ Recall@5 0,9778,
  MRR tăng từ 0,8341 lên 0,8619 trên bộ 50 câu thử nghiệm. BM25/reranker giữ tắt.
- Đã đo retrieval thật trên 50 câu của corpus 58 chunk; wiki API bị 403 nên chưa
  import wiki, reranker đã benchmark nhưng chưa qua gate. Xem [báo cáo nâng cấp](docs/rag_upgrade.md).
- Neo4j Browser: **http://localhost:17474**. Cách chạy, Cypher, snapshot/rollback,
  kết quả và giới hạn đánh giá: [docs/neo4j_demo.md](docs/neo4j_demo.md).
- Ngày 04/11 đã chạy lại 150 test Python, gồm 13 test Neo4j thật; build đạt và
  Playwright 5/5. Một câu chat Gemini thật trên corpus hiện tại trả lời có nguồn
  NIDDK; đây là demo một câu, chưa phải đo lại bộ benchmark sinh câu trả lời.
  Bằng chứng chụp hình được giữ cục bộ trong `artifacts/figure_capture_report.json`;
  ảnh và tài nguyên tạo báo cáo không đưa lên GitHub.

## Công nghệ

React, Vite, TypeScript, Tailwind CSS; FastAPI, Pydantic; PyTorch, Scikit-learn,
Pandas, NumPy, Matplotlib; LangGraph; PyMuPDF, python-docx; Google GenAI SDK; ChromaDB PersistentClient;
Neo4j Community, NetworkX để đối chiếu/rollback;
Pytest và Playwright. Tất cả agent chạy trong một backend FastAPI.

## 1. Cài đặt trên Windows

Chỉ thực hiện phần này khi chưa cài môi trường hoặc cần cài lại thư viện.
Yêu cầu Python 3.11+ 64-bit, Node.js và npm, Internet để cài dependencies.
GraphRAG Neo4j cần thêm Docker Desktop với lệnh `docker compose`; Playwright dùng
Microsoft Edge đã cài trên máy. Nếu Docker Engine chưa chạy, lệnh Neo4j sẽ thất bại.
Đã xác minh với Python 3.13.5, Node 24.13.1. Mở PowerShell tại thư mục dự án:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/setup.ps1
```

Script giữ nguyên `.env` đã có; chọn bản khóa cho Python 3.13 và bản miền phiên
bản cho Python khác. Hoặc cài thủ công theo cùng cách chọn dependency:

```powershell
python -m venv .venv
$pythonMinor = & '.\.venv\Scripts\python.exe' -c 'import sys; print(str(sys.version_info.major) + chr(46) + str(sys.version_info.minor))'
if ($pythonMinor -eq '3.13') {
    .\.venv\Scripts\python -m pip install -r requirements.lock.txt
} else {
    .\.venv\Scripts\python -m pip install -r requirements.txt
}
if (-not (Test-Path -LiteralPath .env)) { Copy-Item -LiteralPath .env.example -Destination .env }
cd frontend
npm ci
cd ..
```

`requirements.lock.txt` khóa các thư viện trực tiếp
đã kiểm thử; `package-lock.json` khóa cây dependency frontend. Các thư viện Python
gián tiếp vẫn do pip giải; dùng cùng phiên bản khi đọc artifact joblib đã lưu.
Nếu dùng Python khác 3.13 và bản khóa không hỗ trợ, cài `requirements.txt` rồi huấn luyện
lại trên môi trường đó; không mặc định artifact Scikit-learn tương thích mọi phiên bản.
`requirements.txt` chứa miền phiên bản cho các môi trường Python tương thích khác.

Không cần activate venv nếu gọi Python bằng đường dẫn như các ví dụ dưới đây.
`-X utf8` giúp console Windows hiển thị tiếng Việt đúng.

## 2. Chạy ứng dụng

### Cấu hình trước khi chạy

Mở `.env` ở **gốc dự án**. Chat cần `GEMINI_API_KEY` hợp lệ để tạo embedding câu hỏi
và sinh trả lời; phân loại PyTorch không dùng key. Trên máy hiện tại key đã được điền,
không cần tạo lại `.env` hoặc thay key nếu chưa có lỗi xác thực/quota.
Giữ `GEMINI_EMBEDDING_MODEL` và `EMBEDDING_DIMENSION` khớp chỉ mục đang có.
Đổi riêng model sinh câu trả lời không yêu cầu index lại.

Để dùng cấu hình vector + Neo4j đã chọn, các cờ trong `.env` là:

```dotenv
GRAPH_BACKEND=neo4j
ENABLE_GRAPH_RETRIEVAL=true
ENABLE_HYBRID_SEARCH=false
ENABLE_WIKI=false
ENABLE_RERANKING=false
FUSION_POLICY=vector_guarded
```

Giữ nguyên key và mật khẩu của máy; khối trên chỉ liệt kê các cờ truy xuất.
Mỗi lần sửa `.env`, dừng API bằng `Ctrl+C` rồi chạy lại vì cấu hình có cache.

### Khi đã có model, ChromaDB và snapshot

Nếu dùng GraphRAG Neo4j, mở Docker Desktop rồi chạy trước:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/run-neo4j.ps1
```

Mật khẩu Browser nằm trong `NEO4J_PASSWORD` của `.env`. Cấu hình máy mới từ
`.env.example` vẫn để graph tắt; bật `ENABLE_GRAPH_RETRIEVAL=true` sau migration.
Khi những dữ liệu này còn đầy đủ, không cần train lại hoặc tạo lại embedding.
Neo4j lỗi có fallback sang vector, hoặc thêm BM25 nếu bật; cấu hình local đang tắt
BM25. Nhánh vector vẫn cần query embedding Gemini, nên lỗi key/quota có thể tiếp
tục làm chat fallback dù đã có tài liệu trong KB.

Terminal 1:

```powershell
.\.venv\Scripts\python -X utf8 -m uvicorn backend.main:app --reload --host 127.0.0.1 --port 8000
```

Terminal 2:

```powershell
cd frontend
npm run dev
```

Hoặc chạy `scripts/run-api.ps1` và `scripts/run-web.ps1` trong hai terminal.
Nếu PowerShell chặn chạy `.ps1`, dùng cú pháp
`powershell -ExecutionPolicy Bypass -File scripts/run-api.ps1` hoặc
`powershell -ExecutionPolicy Bypass -File scripts/run-web.ps1` như phần chạy nhanh.
Mở **http://127.0.0.1:5173**; Swagger ở **http://127.0.0.1:8000/docs**.
Vite proxy `/api` và `/health` sang backend. Nếu Vite đổi cổng do cổng bận,
cập nhật `CORS_ORIGINS` khi gọi API trực tiếp.

`npm run build` kiểm tra TypeScript và xuất frontend vào `frontend/dist/`.
`npm run preview` xem bản build, thường ở cổng 4173. Vite 6 đang cài kế thừa proxy
`/api`, `/health` từ cấu hình dev, nên vẫn gọi được backend local đang chạy ở cổng
8000. Preview không phải máy chủ triển khai production; MVP chưa cấu hình hosting.

### Máy mới chưa có ChromaDB hoặc snapshot

`run-neo4j.ps1` gọi migration dựa trên `data/retrieval/active.json`; vì vậy script
không thay thế bước chuẩn bị dữ liệu lần đầu. Nếu chỉ copy mã nguồn và thiếu dữ
liệu, thực hiện theo thứ tự:

1. Cài môi trường ở mục 1, điền key trong `.env`.
2. Nếu thiếu model, tải CSV và train theo mục 3. Bước này phục vụ phần phân loại.
3. Nếu thiếu tài liệu, lấy nguồn theo mục 4; giữ manifest, ontology và annotation
   đi kèm. Kiểm tra loader rồi index Chroma bằng Gemini thật:

```powershell
.\.venv\Scripts\python -X utf8 -m ingestion.index_documents --check-only
.\.venv\Scripts\python -X utf8 -m ingestion.index_documents
```

4. Mở Docker Desktop. Khởi động database riêng trước khi công bố snapshot đầu tiên:

```powershell
.\.venv\Scripts\python -X utf8 -m ingestion.setup_neo4j
docker compose --progress quiet -f compose.neo4j.yml up -d --wait --wait-timeout 90
.\.venv\Scripts\python -X utf8 -m ingestion.build_retrieval_indexes --activate
```

Chạy từng lệnh sau khi lệnh trước thành công. Lệnh cuối xây graph/BM25 từ Chroma,
migration Neo4j và chỉ ghi `active.json` sau khi kiểm chứng thành công; không gọi
lại embedding. Nếu nguồn mới không còn khớp quote annotation, cần kiểm tra lại
nguồn/annotation trước khi tiếp tục.

5. Đặt các cờ Neo4j như trên, rồi chạy API và giao diện. Những lần mở app tiếp
   theo dùng phần chạy nhanh; không lặp lại quy trình chuẩn bị dữ liệu.

### Kiểm tra đã chạy đủ các phần

Sau khi mở API, xem các URL sau trên trình duyệt hoặc Swagger:

| URL | Dấu hiệu cần thấy |
| --- | --- |
| `http://127.0.0.1:8000/health` | `status=ok`: backend đang chạy |
| `http://127.0.0.1:8000/api/v1/model-info` | `ready=true`: model phân loại nạp được |
| `http://127.0.0.1:8000/api/v1/retrieval-info` | `status=ready`, `graph_enabled=true`, `graph_backend=neo4j`: cấu hình/snapshot đúng |
| `http://127.0.0.1:8000/api/v1/graph/stats` | `connected=true`, `status=ready`: Neo4j thật có snapshot phù hợp |

Cuối cùng hỏi “Tiểu đường là gì?” trên giao diện. Cần có câu trả lời tiếng Việt,
nguồn NIDDK và trace bốn node để xác nhận cả bước Gemini, không chỉ API/database.
Thành công phụ thuộc key/quota tại thời điểm chạy. Số chunk/source trả về có thể
ít hơn top-k nếu không đủ bằng chứng phù hợp.

### Lỗi thường gặp khi mở app

| Hiện tượng | Cách xử lý |
| --- | --- |
| Không tìm thấy `.venv\Scripts\python.exe` hoặc thiếu thư viện | Chạy `scripts/setup.ps1` theo mục 1 |
| Docker báo không kết nối Engine | Mở Docker Desktop, chờ Engine sẵn sàng rồi chạy lại lệnh Neo4j |
| Migration báo thiếu `active.json`/collection | Làm quy trình chuẩn bị lần đầu ở trên; không chỉ khởi động database |
| Model-info `ready=false` | Kiểm tra đủ artifact ở mục 3; chỉ train lại khi thiếu hoặc không tương thích |
| Chat báo thiếu key, hết quota hoặc timeout | Kiểm tra `.env`, key/quota và mã lỗi; không suy ra rằng KB thiếu kiến thức |
| Chat báo “Đoạn trích dẫn không khớp tài liệu nguồn” | Bản nháp trích sai nguyên văn nên Safety chặn; bản sửa cho Gemini chọn mã đoạn và backend lấy quote. Khởi động lại API sau khi cập nhật; không cần index lại |
| Hỏi BMI có số bị báo thiếu bằng chứng | Bản mới đối chiếu BMI qua quy tắc có nguồn. Nếu số khác form hoặc thiếu phạm vi tuổi, hệ thống yêu cầu làm rõ; xem hướng dẫn bản cập nhật |
| Neo4j timeout ngay sau khởi động | Chờ database ổn định rồi thử lại; nếu cần chẩn đoán, xem `NEO4J_QUERY_TIMEOUT_SECONDS` và trace, không xóa volume |
| Cổng 8000/5173 đã có ứng dụng khác | Dừng đúng phiên server cũ bằng `Ctrl+C`; dùng địa chỉ Vite thực tế in ra terminal |

## 3. Dữ liệu thật, EDA và huấn luyện

Đây là bước chuẩn bị model, **không bắt buộc mỗi lần chạy app**. Máy hiện tại đã
có model/scaler/schema/ngưỡng/config; chỉ tải hoặc train lại khi thiếu hay chủ ý
huấn luyện phiên bản mới. Các lệnh EDA/train có thể ghi lại báo cáo và model trong
`artifacts/` theo thư mục đầu ra được chọn.

[UCI CDC Diabetes Health Indicators](https://archive.ics.uci.edu/dataset/891/cdc+diabetes+health+indicators),
DOI `10.24432/C53919`. Script lấy CSV qua API chính thức của UCI, không dùng bản 50/50.
UCI có thể đặt tên tệp là `data.csv`; script lưu vào tên CSV mà đề bài yêu cầu và
ghi nguồn/sha256 bên cạnh. Không tạo dữ liệu giả khi nguồn tải không khả dụng.

```powershell
.\.venv\Scripts\python -X utf8 -m training.download_data
.\.venv\Scripts\python -X utf8 -m training.eda
.\.venv\Scripts\python -X utf8 -m training.train --epochs 30 --seed 42
```

Có thể dùng `--csv <đường-dẫn-CSV>` và `--output <thư-mục-artifact>`.
Nếu tải thủ công, đặt CSV ở `data/raw/diabetes_binary_health_indicators_BRFSS2015.csv`.
Pipeline từ chối schema, missing, mã ngoài miền hoặc target không có hai lớp.
Loại hàng trùng hoàn toàn trước khi chia; các hàng trùng đặc trưng luôn cùng một tập.
Tỷ lệ nhóm khoảng 70/15/15, stratify theo nhãn nhóm; chỉ fit StandardScaler trên train.

Artifacts chính: `model.pt`, `preprocessor.joblib`, `feature_schema.json`, `threshold.json`,
`metrics.json`, `training_config.json`; bổ sung `baseline.joblib`, `data_report.json`
và biểu đồ EDA/calibration. Ngưỡng chọn trên validation theo F1, không dùng test.
Chỉ nạp joblib/model do dự án tin cậy tạo ra. Sau khi train lại, khởi động lại API
để bỏ cache mô hình cũ. Chạy `.\.venv\Scripts\python -X utf8 -m pytest` để kiểm tra artifact.

## 4. Chuẩn bị và index Custom RAG

Máy hiện tại đã có 6 tài liệu, 67 chunk và snapshot. **Không cần tải/index lại để
mở chat**. Đánh giá RAG là bước đo chất lượng riêng, không phải điều kiện khởi động
ứng dụng và sẽ gọi Gemini thật.

Kho hiện tại có 6 bản văn bản NIDDK về tổng quan, triệu chứng, yếu tố nguy cơ,
phòng ngừa, xét nghiệm và BMI. [Điều kiện sử dụng NIDDK](https://www.niddk.nih.gov/copyright)
cho phép dùng phần lớn thông tin nhưng có ngoại lệ; pipeline không sao chép ảnh/logo,
không ngụ ý NIDDK bảo trợ ứng dụng. Cần kiểm tra lại nội dung và ngày cập nhật nguồn
khi sử dụng. Bản tài liệu giữ nguyên tiếng Anh; Gemini trả lời tiếng Việt.

Tải lại nguồn khi cần:

```powershell
.\.venv\Scripts\python -X utf8 -m ingestion.download_sources
```

Trong `.env` backend, điền `GEMINI_API_KEY` của bạn. Không đưa khóa vào chat, frontend,
Git hay tài liệu. Model được cấu hình bằng `GEMINI_EMBEDDING_MODEL` và `GEMINI_LLM_MODEL`;
kiểm tra model/quota khả dụng trên tài khoản của bạn. Mặc định LLM `gemini-2.5-flash`,
đã trả lời được khi kiểm thử live bằng tài khoản hiện tại ngày 01/11/2026.
`gemini-3.8-flash` có trong danh sách model của tài khoản nhưng trả lỗi 504 ở các lần thử.
Có thể chọn model khác qua `.env` theo khả năng truy cập thực tế; không cần index lại
khi chỉ đổi LLM, vì embedding model vẫn giữ nguyên.

```powershell
.\.venv\Scripts\python -X utf8 -m ingestion.index_documents
.\.venv\Scripts\python -X utf8 -m evaluation.evaluate_rag --output artifacts/rag_metrics_current.json
```

Evaluator mặc định nghỉ 7 giây giữa các câu để giảm lỗi giới hạn số request/phút.
Có thể đổi bằng `--delay-seconds 10`; khoảng nghỉ không được tính vào latency xử lý.
Khoảng nghỉ không khắc phục quota theo ngày hoặc hạn mức token của tài khoản.

GraphRAG/BM25 có thể xây từ embedding đang có, không gọi Gemini lại:

```powershell
.\.venv\Scripts\python -X utf8 -m ingestion.build_retrieval_indexes --activate
.\.venv\Scripts\python -X utf8 -m evaluation.demo_graph --case-id r36
```

`POST /api/v1/retrieve` nhận thêm `retrieval_mode=graph` để demo nguồn/đường đi,
không sinh câu trả lời LLM. Mode `graph` là **vector + graph**, `hybrid_graph` thêm
BM25; cả hai vẫn thử gọi query embedding. Lệnh `evaluation.demo_graph` dùng query
embedding thật đã cache nên không gọi Gemini lại, nhưng cần Neo4j khi chọn backend này.
Chat dùng các cờ trong `.env`; cấu hình local hiện chọn
vector + Neo4j. `.env.example` giữ cờ nâng cao tắt cho máy mới. Hướng dẫn wiki,
snapshot và benchmark giai đoạn trước: [docs/rag_upgrade.md](docs/rag_upgrade.md).

Index đọc `data/knowledge/manifest.json`; hỗ trợ PDF có text, DOCX, TXT UTF-8 và Markdown,
chỉ chấp nhận các miền nguồn đã duyệt. PDF có trang thiếu text sẽ báo trang cần kiểm tra/OCR,
không index thiếu trang. OCR/ảnh và DOC cũ chưa hỗ trợ. Chunk theo heading/câu,
mục tiêu tối đa khoảng 500 token và overlap tối đa khoảng 50 token (ước lượng ký tự).
Các mục ngắn có chunk nhỏ; câu dài và bảng giữ nguyên để không cắt tùy tiện.
DOCX giữ thứ tự paragraph/bảng và heading; metadata bổ sung `source_type`, `section_path`.
Chi tiết định dạng, schema, giới hạn và báo cáo: [docs/ingestion.md](docs/ingestion.md).

Kiểm tra dữ liệu offline trước khi index; có thể chọn riêng tài liệu bằng ID:

```powershell
.\.venv\Scripts\python -X utf8 -m ingestion.index_documents --check-only
.\.venv\Scripts\python -X utf8 -m ingestion.index_documents --document-id niddk-tests
```

Lệnh index tự bỏ qua tài liệu có nội dung và metadata chunk không đổi, không gọi Gemini
cho phần này. `--check-only` không gọi Gemini hoặc ChromaDB, không cần API key.
`index_documents` chỉ cập nhật Chroma từng tài liệu. Nếu nội dung thay đổi, cần kiểm
tra lại annotation và công bố snapshot graph/BM25 tương ứng; xem
[quy trình cập nhật](docs/neo4j_demo.md#migration-cập-nhật-và-rollback).

Gemini embedding dùng task `RETRIEVAL_DOCUMENT` / `RETRIEVAL_QUERY`, dimension 768,
chuẩn hóa L2. Chroma cosine, top-k mặc định 5, lọc khoảng cách cosine > 0,65.
Ngưỡng này là cấu hình khởi đầu, **chưa tối ưu trên tập đánh giá live**.
Khi sinh câu trả lời, Gemini chọn mã đoạn bằng chứng; backend lấy trích dẫn nguyên
văn từ nguồn rồi vẫn kiểm tra ID, quote, số liệu và quy tắc an toàn. Cách này tránh
lỗi Gemini đảo câu hoặc bỏ dòng khi tự chép trích dẫn. Nếu vừa cập nhật phần này,
khởi động lại API bằng `scripts/run-api.ps1`; không cần train hoặc index lại.
Re-index tài liệu thay đổi là idempotent và loại chunk cũ của chính tài liệu đó;
xóa mục khỏi manifest chưa tự động xóa chunk trong ChromaDB. Đổi model/dimension phải
dùng `CHROMA_COLLECTION` mới và re-index; không trộn các không gian embedding.

Evaluator mặc định ghi đè `artifacts/rag_metrics.json`; bản đang lưu là kết quả lịch
sử trên 55 chunk. Lệnh trên chọn tên mới để giữ báo cáo đó. Đầu ra gồm Recall@K,
MRR, tỷ lệ claim qua kiểm tra
ID/quote và latency. Groundedness ngữ nghĩa cần chấm tay theo hướng dẫn trong
[docs/evaluation.md](docs/evaluation.md); không giả định quote hợp lệ chứng minh claim đúng.
Nếu LLM lỗi sau khi truy xuất thành công, Recall@K/MRR vẫn được tính từ những câu đã
truy xuất; `cases_completed` chỉ đếm các câu hoàn tất toàn bộ pipeline.
`results[].error_codes` giúp phân biệt lỗi model, quota, timeout và JSON đầu ra không hợp lệ.
`answer_cases_passed` và `answer_cases_fallback` tách câu trả lời vượt kiểm tra khỏi
các câu đã xử lý xong nhưng phải phản hồi giới hạn; `status=completed` không có nghĩa
mọi câu đều đạt kiểm tra citation hoặc groundedness.

## 5. API

| Endpoint | Nội dung |
| --- | --- |
| `GET /health` | Backend hoạt động; không đồng nghĩa Gemini/model sẵn sàng |
| `GET /api/v1/model-info` | Trạng thái model, version, thứ tự đặc trưng, ngưỡng, giới hạn |
| `POST /api/v1/scenarios` | Thử thay đổi đầu vào, giữ hồ sơ gốc và so sánh trước–sau |
| `POST /api/v1/models/compare` | So sánh MLP và Logistic Regression theo ngưỡng riêng |
| `GET /api/v1/model-inspection` | Báo cáo ảnh hưởng chung khớp trọng số/scaler |
| `POST /api/v1/dataset/query` | Thống kê nhãn khảo sát theo bộ lọc cho phép |
| `POST /api/v1/predict` | `{ "patient_features": { ...21 trường... } }` → kết quả mô hình |
| `POST /api/v1/chat` | `{ "user_query": "Tiểu đường là gì?" }` → trả lời, nguồn và trace |
| `POST /api/v1/analyze` | Features và/hoặc câu hỏi → workflow theo intent |
| `GET /api/v1/retrieval-info` | Cờ tính năng và snapshot local; không xác minh kết nối Neo4j |
| `GET /api/v1/graph/stats` | Truy vấn Neo4j thật để kiểm tra snapshot và số node |
| `POST /api/v1/retrieve` | Trả chunk và đường truy xuất; không sinh câu trả lời LLM |

Mẫu payload dành cho demo: [docs/sample_request.json](docs/sample_request.json).
Chỉ là đầu vào minh họa, không phải bệnh án hay dữ liệu để đo chất lượng.
Thiếu/sai dữ liệu: 422. `/predict` thiếu hoặc hỏng artifact: 503.
Chat/analyze khi Gemini lỗi hoặc thiếu bằng chứng trả 200 với `safety_status=fallback`,
`errors` rõ ràng và không gắn citation giả. Lỗi nội bộ khác trả 500 không lộ nội dung.
`X-Request-ID` khớp ID trong response, trace có latency thực của từng node.

21 trường và quy tắc ánh xạ: [docs/data_dictionary.md](docs/data_dictionary.md).
Không nhập tuổi thật vào `Age`: đây là mã nhóm 1–13, không phải số tuổi.

## 6. Kiểm thử

```powershell
.\.venv\Scripts\python -X utf8 -m pytest
.\.venv\Scripts\python -X utf8 -m compileall -q backend training ingestion evaluation tests
.\.venv\Scripts\python -m pip check
cd frontend
npm run build
npm run test:e2e
```

Playwright dùng Microsoft Edge đã cài sẵn và tự chạy API/Vite local trên cổng 8000/5173;
dừng các phiên dev trước khi chạy. Test trình duyệt kiểm tra model artifact thật và
fallback khi thiếu key, tự đặt `GEMINI_API_KEY` rỗng cho process API test, giữ nguyên `.env`.
Có thể đổi `channel`
trong `frontend/playwright.config.ts` nếu môi trường không có Edge.
Khi snapshot dùng Neo4j, cần mở Docker/Neo4j trước cả test trình duyệt: một test
GraphRAG gọi database thật, dù process API test không có Gemini key.

Để chạy cả 13 test Neo4j của Python, đứng ở gốc dự án và dùng:

```powershell
$env:NEO4J_INTEGRATION = '1'
.\.venv\Scripts\python -X utf8 -m pytest
Remove-Item Env:\NEO4J_INTEGRATION
```

Nếu Pytest báo `PermissionError` với thư mục `pytest-of-Admin` cũ trong Temp,
dùng một thư mục tạm mới chỉ dành cho lần chạy đó:

```powershell
$pytestRunDir = Join-Path $env:TEMP ('glucoguide-pytest-' + [guid]::NewGuid().ToString('N'))
.\.venv\Scripts\python -X utf8 -m pytest --basetemp $pytestRunDir
```

Nếu muốn kiểm thử Neo4j trong lần dùng thư mục tạm mới, đặt lại
`$env:NEO4J_INTEGRATION = '1'` trước lệnh pytest và gỡ biến sau khi xong.

Kiểm thử tích hợp model và nguồn thật sẽ skip nếu chưa chuẩn bị artifact/tài liệu.
Unit test mock Gemini, dùng ChromaDB tạm thời; không báo metrics mock như chất lượng RAG.
Lần kiểm tra gần nhất ngày **04/11/2026**: **150 passed**, gồm **13 test Neo4j thật** khi đặt
`NEO4J_INTEGRATION=1`. Nếu không đặt biến này, 13 test đó sẽ skip. Cách chạy có Neo4j
và lệnh tái lập nằm trong [neo4j_demo.md](docs/neo4j_demo.md#kiểm-thử-và-tái-lập).
Sau dọn dẹp, `frontend/test-results/` chưa có; chạy Playwright sẽ tạo lại ảnh/báo cáo.

## 7. Tài liệu và giới hạn

- [Kiến trúc và luồng Agent](docs/architecture.md)
- [Báo cáo đánh giá thực tế](docs/evaluation.md)
- [Kịch bản demo](docs/demo.md)
- [Nhật ký kiểm chứng theo phase](docs/implementation.md)
- [Loader, định dạng và chunking](docs/ingestion.md)
- [GraphRAG Neo4j hiện tại](docs/neo4j_demo.md)
- [Báo cáo nâng cấp giai đoạn NetworkX](docs/rag_upgrade.md)

File prompt giao việc, báo cáo Word/PDF và tài nguyên tạo báo cáo được giữ cục bộ,
không thuộc repository công khai. Các số đo cũ trong nhật ký được giữ theo từng giai đoạn.

Giới hạn: dữ liệu khảo sát tự báo cáo năm 2015 ở Hoa Kỳ, nhãn gộp, lệch phân bố dân số;
chưa đánh giá trên dân số Việt Nam. Class weights và chọn ngưỡng F1 không làm score
trở thành xác suất y khoa. Safety/citation validators dùng quy tắc, có thể bỏ sót nội dung
không an toàn hoặc suy diễn thiếu căn cứ. Cần đánh giá thủ công trước mọi ứng dụng ngoài đồ án.
Câu hỏi được gửi tới Gemini để embedding/sinh trả lời; không nhập dữ liệu định danh
vào chat. 21 đặc trưng không được gửi cho Gemini, chỉ suy luận local; ở nhánh kết hợp,
LLM chỉ nhận kết quả mô hình tổng quát và câu hỏi. Không có xác thực, quản lý bệnh án,
hosting production hay lưu lịch sử người dùng trong MVP.
