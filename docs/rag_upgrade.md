# Nâng cấp Custom RAG — giai đoạn NetworkX ngày 03/11/2026

> Báo cáo giai đoạn NetworkX trước migration Neo4j, giữ nguyên để đối chiếu.
> Trạng thái hiện tại, fusion mới và cấu hình local: [neo4j_demo.md](neo4j_demo.md).
> Hiện local đã bật vector + Neo4j với `vector_guarded`. Các quyết định “chưa bật”
> và số 125 test dưới đây thuộc giai đoạn cũ, không mô tả cấu hình local hiện tại.

Đã bổ sung Custom GraphRAG local, BM25/RRF, adapter MediaWiki và reranker tùy chọn.
Giữ FastAPI, LangGraph, PyTorch, Custom Chunking, Gemini Embedding và ChromaDB.
**Ở thời điểm báo cáo NetworkX, chat dùng vector retrieval** vì các nhánh mới chưa
vượt đủ kiểm định chất lượng. API demo có thể chọn graph mà không đổi cấu hình chat.

## Trạng thái tại giai đoạn NetworkX

| Thành phần | Đã làm | Trạng thái sử dụng |
| --- | --- | --- |
| Baseline | Lưu nguồn, 58 chunk, vector, cấu hình và gold trong `artifacts/baseline_niddk/` | Giữ nguyên collection `diabetes_knowledge` |
| GraphRAG | 36 thực thể, 36 quan hệ, 38 evidence; entity linking Việt–Anh; tối đa 2 bước | Đã demo bằng nguồn thật; chưa bật mặc định |
| Hybrid | BM25, từ điển kiểm soát, RRF theo chunk ID, không trộn thang điểm | Đã đo thật; chưa bật mặc định |
| Wiki | 3 bài trong danh sách duyệt, khóa revision, phần mở đầu, giấy phép, retry | API thực trả HTTP 403 robot policy; chưa import bài/chunk wiki nào |
| Reranker | Process CPU nạp lười, model cache local, timeout, cooldown, fallback | Đã benchmark 50 câu thật; không qua gate, giữ tắt |
| Microsoft GraphRAG đầy đủ | Không triển khai community detection/global search | Ngoài phạm vi |

Source annotation và gold do agent đối chiếu với văn bản nguồn, **chưa được bác sĩ
hoặc người đánh giá độc lập duyệt**. Không diễn giải chúng thành tri thức y khoa
đã được kiểm định lâm sàng.

## Entity, Relation và Evidence

`data/knowledge/ontology.json` định nghĩa thực thể và bí danh; không lấy liên kết
Wikipedia hoặc việc hai từ đồng xuất hiện làm quan hệ y khoa tự động.
`data/knowledge/graph_annotations.json` chứa các quan hệ ban đầu đã đối chiếu nguồn.

- **Entity:** ID chuẩn, tên, loại, bí danh Việt–Anh. Ghép bí danh dài trước để giữ
  riêng típ 1/típ 2 và tránh tên chung che tên bệnh cụ thể.
- **Relation:** ID, subject, predicate, object, polarity và qualifiers. Có hướng;
  không mặc định đối xứng hoặc bắc cầu. MVP không cho phép predicate `CAUSES`.
- **Evidence:** ID riêng cho từng nguồn/quote, relation ID, document/chunk ID,
  content version, URL, provider, quote, trạng thái và người/agent kiểm tra.
  Hai nguồn nói về cùng quan hệ được giữ thành hai evidence record độc lập.

`polarity` áp dụng cho mệnh đề viết trong predicate. Ví dụ `CANNOT_DIAGNOSE` đã
chứa nghĩa không có khả năng chẩn đoán; polarity `positive` khẳng định chính
mệnh đề đó, không đảo nghĩa thành có thể chẩn đoán.

Các loại quan hệ đang cho phép: HAS_SUBTYPE, HAS_ASSOCIATED_SYMPTOM,
RISK_FACTOR_FOR, ASSOCIATED_WITH, USED_TO_ASSESS, MEASURES,
MAY_REDUCE_RISK_OF, CANNOT_DIAGNOSE và PRODUCES.

Graph ở giai đoạn này dùng NetworkX MultiDiGraph; hiện backend chính là Neo4j.
Có thể duyệt ngược cạnh để tìm tài liệu, nhưng
trace luôn giữ nguyên hướng/ngữ nghĩa cạnh gốc. Đường hai bước mang evidence của
từng cạnh; không tạo kết luận nhân quả giữa hai đầu mút. LLM nhận chunk nguồn,
không nhận một kết luận bắc cầu do graph tự suy ra.

Ứng viên graph được xếp theo độ phủ thực thể, khớp loại quan hệ với ý định, số bước,
chất lượng nguồn/trạng thái kiểm tra và ID ổn định. Không dùng thứ tự BFS ngẫu nhiên.
Một truy vấn chỉ có một thực thể và không có ý định hỏi quan hệ không được mở rộng
graph tùy tiện. Đây là quy tắc định tuyến có giới hạn, chưa phải entity linker học máy.

Có CLI Gemini trích quan hệ **nháp** bằng JSON schema. Chỉ gọi cho chunk chưa cache:

```powershell
.\.venv\Scripts\python -X utf8 -m ingestion.extract_graph --document-id niddk-tests
```

Nháp có `status=draft`, không được graph compiler phục vụ. Cần kiểm tra ngữ nghĩa,
điều kiện/phủ định và quote, rồi đưa annotation được duyệt vào file nguồn với danh
tính người kiểm tra thật. Không đổi `checked_by` thành tên bác sĩ/người dùng nếu họ
chưa duyệt. Chưa chạy trích nháp Gemini cho toàn bộ corpus trong đợt này; graph thật
hiện dùng annotation đã đối chiếu từ NIDDK. Unit test extractor dùng client mock.

## Snapshot và cập nhật an toàn

`data/retrieval/active.json` trỏ đến một bundle bất biến dưới `snapshots/<id>/`:

- `corpus.json`: nội dung/metadata chuẩn hóa theo chunk ID.
- `graph.json`: entity/relation/evidence cùng `corpus_version`.
- `lexical.json`: thứ tự ID, token và phiên bản tokenizer BM25.
- `manifest.json`: corpus/graph/config hash, collection và checksum từng file.

Loader kiểm tra checksum, ID, URL, quote, phiên bản evidence và hash dữ liệu Chroma.
Trước khi trả kết quả còn kiểm tra collection chưa đổi trong lúc truy xuất. Nếu
không khớp, dùng pipeline vector cũ và ghi warning; không ghép graph mới với corpus cũ.

Xây snapshot từ Chroma hiện có không tạo lại embedding:

```powershell
.\.venv\Scripts\python -X utf8 -m ingestion.build_retrieval_indexes --activate
```

Khi bổ sung wiki, publisher chuẩn bị collection mới, tái sử dụng vector văn bản
không đổi, chỉ embed văn bản mới rồi kiểm tra bundle trước khi thay con trỏ active.
Collection baseline và các snapshot trước được giữ lại. Đây không phải transaction
phân tán: tính nhất quán được bảo đảm bằng collection/version bất biến, kiểm tra
hash và công bố con trỏ sau cùng. Chưa hỗ trợ nhiều tiến trình ghi index đồng thời;
chạy từng job ingestion/publish một lần.

Nếu cập nhật collection baseline bằng lệnh indexing cũ, cần build lại snapshot.
Annotation có quote không còn khớp sẽ chặn công bố graph mới, yêu cầu đối chiếu lại;
không tự tái sử dụng quan hệ đã hết hiệu lực.

## Hybrid và reranking

Vector search giữ lọc cosine distance 0,65 của baseline. BM25 giữ truy vấn gốc và
thêm tên chuẩn tiếng Anh từ từ điển; không gọi LLM dịch từng câu.
Vector/BM25/graph trả cùng kiểu Evidence. Chỉ nhánh vector có `distance`; điểm BM25
và graph không được giả thành khoảng cách cosine.

RRF hợp nhất danh sách đã xếp hạng, loại trùng bằng chunk ID, từ chối cùng ID nhưng
khác nội dung/metadata. `RRF_CONSTANT=60` khác với `RETRIEVAL_K=5`.
Mặc định lấy tối đa 15 ứng viên mỗi nhánh và chọn tối đa 5 chunk cuối; context vẫn
giữ ngân sách 14.000 ký tự và kiểm tra citation/Safety như trước.

Reranker là bước riêng sau RRF. Process model dùng CPU 2 thread, max length 384,
batch 4, mặc định tối đa 15 ứng viên. Không import transformers hoặc nạp model khi
tính năng tắt. Process phục vụ chỉ đọc cache local, không tự tải model khi chat.
Lỗi/timeout dừng worker và trả nguyên thứ tự RRF, có cooldown 30 giây.

Dependency model là tùy chọn:

```powershell
.\.venv\Scripts\python -m pip install -r requirements-rerank.txt
.\.venv\Scripts\python -X utf8 -m evaluation.benchmark_reranker --download
```

Benchmark cho phép tải model rõ ràng, khóa revision và giới hạn tổng thời gian tải
180 giây. Model cache ở `artifacts/reranker_cache/`, đã được gitignore. Đây là cache
riêng, có thể tốn vài trăm MB; không nằm trong yêu cầu cài đặt base khi tắt reranker.
Cache model thử nghiệm đã được dọn trong lần vệ sinh dự án; muốn thử lại cần
chạy benchmark với `--download` để tải lại. Giữ nguyên code và báo cáo benchmark cũ.

## Wiki

`data/wiki/manifest.json` chọn 3 bài: Glycated hemoglobin, Insulin resistance,
Blood sugar level. Chỉ lấy **phần mở đầu** qua `action=parse`, `oldid`, `section=0`;
không ghi là đã lấy toàn bài. Dữ liệu lưu JSON trực tiếp theo cấu trúc Document.

Metadata giữ nguyên `source_type=html` là định dạng parser, bổ sung provider,
parser_format, language, page/revision ID, revision timestamp, content_version,
URL phiên bản, attribution/license, retrieved_at, checksum và các thay đổi định dạng.
URL nguồn Wikipedia chỉ chấp nhận en/vi, HTTPS và một `oldid` dương rõ ràng.

Request có User-Agent nhận diện ứng dụng; nên cấu hình thông tin liên hệ thật của
nhóm qua `WIKI_USER_AGENT`. Client giới hạn request, tôn trọng Retry-After, retry
429/maxlag hữu hạn, dừng khi 403. Không đổi endpoint để vượt chặn robot policy.

Sau khi quyền truy cập nguồn hoạt động và kiểm tra nội dung:

```powershell
.\.venv\Scripts\python -X utf8 -m ingestion.wiki_sources
.\.venv\Scripts\python -X utf8 -m ingestion.publish_corpus --activate
```

Không chạy lệnh publish khi wiki download còn lỗi/missing. Publisher nạp và kiểm
tra đủ các bài trong manifest trước khi mở collection để cập nhật. Chạy lại cùng
revision/nội dung không ghi lại document và không tạo embedding thừa.

Wiki chỉ là nguồn định nghĩa/kiến thức nền. Bộ lọc không dùng wiki cho câu hỏi điều
trị, ngưỡng, nguy cơ hoặc khuyến nghị. Safety còn loại claim chỉ dựa vào wiki nhưng
đưa ra số đo hoặc khuyến nghị y khoa. Đây là kiểm tra quy tắc, chưa thay thế đánh giá
ngữ nghĩa thủ công. Graph compiler giới hạn quan hệ nền từ wiki; chưa tự khai thác
toàn bộ Wikipedia thành graph lâm sàng. UI có attribution, revision và license khi
citation wiki thực sự được dùng.

**Lượt API thật trả 403; hiện có 0 bài và 0 chunk wiki được xuất bản.** Parser, retry,
revision và publishing được test bằng HTTP/vector mock trong dữ liệu tạm; không
dùng số liệu mock để báo đã import nguồn thật.

## Demo và cấu hình

Không cần gọi API lại để xem demo nguồn NIDDK đã cache:

```powershell
.\.venv\Scripts\python -X utf8 -m evaluation.demo_graph --case-id r36
```

Đầu ra lưu `artifacts/graph_demo.json`: thực thể nhận diện, quan hệ có hướng,
evidence/quote/version, chunk IDs và `used_in_context`. Đây là demo retrieval/context,
không giả lập câu trả lời LLM hoặc kết quả PyTorch.

Khi API đang chạy, `GET /api/v1/retrieval-info` báo snapshot và cờ tính năng.
`POST /api/v1/retrieve` chấp nhận:

```json
{
  "user_query": "Tiền tiểu đường liên quan nguy cơ típ 2 và thay đổi lối sống nào có thể giúp trì hoãn?",
  "retrieval_mode": "graph"
}
```

Các mode: `configured`, `vector`, `graph`, `hybrid_graph`. Endpoint không gọi LLM sinh
trả lời; nếu thiếu embedding key mà snapshot hợp lệ, BM25/graph vẫn có thể tìm nguồn
local. Chat thông thường vẫn cần LLM để sinh câu trả lời.

Các cờ trong `.env.example` hiện đều false:

```dotenv
ENABLE_GRAPH_RETRIEVAL=false
ENABLE_HYBRID_SEARCH=false
ENABLE_WIKI=false
ENABLE_RERANKING=false
```

Trên máy mới, chỉ bật `ENABLE_GRAPH_RETRIEVAL=true` sau khi chuẩn bị backend và
migration thành công, rồi khởi động lại API. Local hiện đã bật graph; không cần bật
lại. Thử BM25 thêm `ENABLE_HYBRID_SEARCH=true`; cấu hình này chưa qua kiểm định
chất lượng. Tắt các cờ sẽ quay về vector; không phải xóa/index lại Chroma.
Phần `.env.example` trên là mẫu khởi tạo, không phải bản sao `.env` của máy hiện tại.

`retrieval_mode=graph` là vector + graph, `hybrid_graph` thêm BM25. Endpoint thử
query embedding và chỉ dùng nguồn local nếu embedding lỗi mà local vẫn có kết quả.
Lệnh `evaluation.demo_graph` dùng backend/fusion đang cấu hình trong `.env`; với
local hiện tại nó chạy Neo4j và cần database sẵn sàng. Không coi kết quả lệnh này
là tái lập NetworkX cũ. Muốn đối chiếu giai đoạn cũ, dùng lệnh có tham số backend
và fusion rõ ràng ở phần tái lập bên dưới.

## Kết quả đo thật

50 câu được gán quote nguồn rồi đóng băng cùng baseline, gồm 45 câu có gold và 5 câu
thiếu bằng chứng/ngoài phạm vi. Tạo embedding query thật bằng 4 batch Gemini, các
lần ablation dùng lại cache, không gọi Gemini sinh câu trả lời.

| Retrieval trên cùng 58 chunk | Recall@5 | MRR | nDCG@5 |
| --- | ---: | ---: | ---: |
| Vector | 0,9778 | 0,8341 | 0,8617 |
| Vector + BM25 | 0,8667 | 0,7322 | 0,7512 |
| Vector + graph | 0,9333 | 0,8500 | 0,8722 |
| Vector + BM25 + graph | 0,8667 | 0,7711 | 0,7924 |

Graph cải thiện thứ hạng ở r05/r07/r36/r42, suy giảm ở r21/r24/r45. Trên gold hiện
tại, **chưa có câu graph bổ sung gold evidence mới ngoài top-5 vector**. Unit test
corpus phần mềm có kiểm chứng nhánh graph tìm được chunk ngoài kết quả vector;
không coi đó là hiệu quả truy xuất y khoa thật. Demo nguồn thật xác nhận graph
tham gia chọn/rank context và có đường đi hai bước với provenance.

Kết quả ban đầu được giữ ở `retrieval_ablation_niddk_initial.json`; sau sửa quy tắc
không mở rộng graph khi thiếu ý định hỏi quan hệ, lưu ở `retrieval_ablation_niddk.json`.
Không sửa gold để làm đẹp kết quả. Phân chia development/heldout được cố định nhưng
agent đã xem các báo cáo trong quá trình sửa; **không phải test mù độc lập**. Các
con số chỉ là kiểm chứng thăm dò, cần gold/annotation do người độc lập duyệt.

Reranker thử: `cross-encoder/mmarco-mMiniLMv2-L12-H384-v1`, revision
`1427fd652930e4ba29e8149678df786c240d8825`. Chạy đủ 50/50 câu; RSS đỉnh parent + worker
1.113.243.648 byte (~1,04 GiB); RAM máy thực tế 23,69 GiB. Warm p95 5.604 ms, vượt
gate 5.000 ms. Trên phần heldout, Recall/MRR giảm từ 0,9000/0,8000 của RRF xuống
0,8833/0,7761 sau rerank. Không bật mặc định. Kết quả này không phải benchmark trên
máy 16 GB và RSS đo không bao gồm mọi ứng dụng khác trong hệ thống.

Latency retrieval trong ablation dùng embedding đã cache, **không phải latency
chat end-to-end**. Citation correctness, groundedness và relation precision do
người chấm vẫn chưa đo trong đợt này; không điền điểm giả vào các chỉ số đó.
Chưa làm vòng B NIDDK + wiki vì API wiki đang chặn truy cập.

Lệnh tái lập (không gọi API nếu cache đủ):

```powershell
.\.venv\Scripts\python -X utf8 -m evaluation.evaluate_retrieval --graph-backend networkx --fusion-policy rrf --output artifacts/retrieval_ablation_niddk_recheck.json
```

`evaluation.upgrade_report` tổng hợp cố định bộ ablation NetworkX/RRF cũ vào
`artifacts/rag_upgrade_report.json`; trường rollout của nó không phản ánh cấu hình
Neo4j hiện tại. Báo cáo hiện tại dùng `evaluation.neo4j_report` như hướng dẫn Neo4j.

## Các file chính

- `backend/rag/`: models, corpus, lexical, fusion, knowledge_graph, snapshot,
  source_policy, reranker; tích hợp vào retriever/context_builder hiện có.
- `ingestion/`: build_retrieval_indexes, wiki_sources, publish_corpus, extract_graph;
  mở rộng kiểm tra URL trong document_loader. Giữ Custom Chunking hiện tại.
- `evaluation/`: retrieval_gold, evaluate_retrieval, benchmark_reranker, demo_graph,
  upgrade_report. Bộ đánh giá sinh câu trả lời cũ vẫn dùng được.
- `backend/agents/`, `backend/graph/`, API schema/routes: thêm retrieval trace,
  policy wiki, endpoint demo; không đổi cơ chế điều phối hoặc mô hình phân loại.
- Frontend Answer/types: đọc attribution wiki và đường tìm evidence khi có trace.
- Dependency/config: requirements base/lock, requirements-rerank tùy chọn,
  `.env.example`, `.gitignore`. Không sửa key hoặc training artifacts.
- Các test mới: graph/hybrid, wiki, publish corpus, extractor, evaluator, reranker,
  API; Playwright bổ sung API graph local và render wiki attribution/graph path.

Các báo cáo máy đọc được: `artifacts/rag_upgrade_report.json`,
`artifacts/retrieval_ablation_niddk.json`, `artifacts/reranker_benchmark.json`,
`artifacts/graph_demo.json` và `data/wiki/download_report.json`.

## Kiểm thử hoàn tất tại giai đoạn NetworkX

- Pytest: **125 passed**, 6 DeprecationWarning joblib/NumPy đã có trước.
- Ruff và compileall: đạt; `pip check`: không có dependency lỗi.
- TypeScript/Vite build: đạt.
- Playwright Edge headless: **5 passed**, gồm API GraphRAG local dùng snapshot thật
  khi process test không có Gemini key, và render wiki attribution/đường đi bằng
  fixture UI. Fixture không được coi là wiki đã tải hoặc câu trả lời Gemini thật.
