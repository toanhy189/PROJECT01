# Phương án phát triển GlucoGuide từ các ý tưởng trong Diabetes Arena

Ngày đối chiếu: 05/11/2026.

Đây là bản phương án ban đầu. **Đã triển khai các phần chính ngày 05/11/2026**;
xem [chức năng thực tế và cách dùng](development_upgrade.md). Các phần tùy chọn
như SSE, SHAP, sân khấu 3D và lưu lâu dài chưa triển khai. Các mô tả “đề xuất”
ở dưới giữ làm hồ sơ thiết kế, không thay thế báo cáo trạng thái thực tế.
Đối chiếu với code GlucoGuide và báo cáo PDF 32 trang
`Project01_CT_09_Hieupm.310.pdf` do người dùng cung cấp. Các nhận xét về
Diabetes Arena dựa trên báo cáo; chưa kiểm chứng repository của project đó.

## 1. Mục tiêu và phạm vi

Phát triển theo ba hướng có thể kiểm chứng:

1. Trả lời đúng phạm vi câu hỏi, phân biệt thông tin người dùng với bằng chứng.
2. Giúp người dùng hiểu và thử hành vi của mô hình ML/DL đang chạy.
3. Cho phép mở lại nguồn và đường truy xuất Neo4j ngay trong ứng dụng.

Giữ React, FastAPI, LangGraph, PyTorch, Gemini Embedding, ChromaDB,
Neo4j và Custom Chunking. Các chức năng mới là dịch vụ nhỏ được gọi từ
workflow hiện có; không cần tạo một agent mới cho mỗi công cụ.

Chưa đưa vào phạm vi đợt đầu: sân khấu 3D, thêm nhiều mạng nơ ron,
đào tạo lại tự động, OCR, Microsoft GraphRAG đầy đủ, đăng nhập nhiều người,
lưu bệnh án lâu dài hoặc dự đoán nguy cơ mắc bệnh trong tương lai.

## 2. Những gì đã có và còn thiếu

| Hạng mục | Hiện trạng được đối chiếu | Phần cần phát triển |
| --- | --- | --- |
| MLP | Nhận 21 đầu vào, dùng scaler đã lưu, trả điểm/lớp/ngưỡng/version | Giải thích và so sánh trước–sau trên giao diện |
| Logistic Regression | Có `baseline.joblib` và ngưỡng riêng trong `metrics.json` | Dịch vụ suy luận và thẻ so sánh với MLP |
| RAG | 5 tài liệu NIDDK, 58 chunk; Gemini chọn mã đoạn, backend lấy quote gốc | Bổ sung nguồn BMI và kiểm tra quan hệ giữa nhận định với bằng chứng |
| GraphRAG | Neo4j thật, truy xuất có snapshot và đường truy nguồn | Đồ thị tương tác trong React |
| Kiểm tra trích dẫn | Kiểm tra ID, quote, số liệu và một số quy tắc an toàn | Tách số đầu vào; kiểm tra ngữ cảnh của ngưỡng và ý nghĩa câu |
| Chat | Có lịch sử hiển thị ở trình duyệt; backend xử lý độc lập từng câu | Câu hỏi nối tiếp gắn đúng hồ sơ và lần phân tích |
| Giải thích mô hình | Có `artifacts/ml_feature_importance.json` đo mức phụ thuộc chung | API đọc báo cáo và thử độ nhạy riêng cho hồ sơ |
| API | Có `/predict`, `/chat`, `/analyze`, `/retrieve`, `/model-info`, `/retrieval-info`, `/graph/stats` | Endpoint chuyên trách cho các công cụ mới |

Các số lượng trên là mốc hiện tại, không phải số cố định sau khi bổ sung nguồn.

## 3. Đợt A — Hoàn thiện câu trả lời và thử thay đổi đầu vào

### A1. Trả lời câu hỏi có số người dùng cung cấp

Ví dụ mục tiêu: “BMI 59 của mình có quá cao không?”.

Luồng xử lý đề xuất:

1. Nhận biết người dùng đang hỏi kiến thức, đánh giá một thông số, dự đoán
   từ đủ 21 đầu vào, hay thử thay đổi hồ sơ. Câu mơ hồ phải được hỏi lại.
2. Tách thông số rõ ràng từ câu hỏi thành dữ liệu có cấu trúc, chẳng hạn
   `name=BMI`, `value=59`, `origin=user_question`. Nếu giá trị đến từ form,
   ghi `origin=form` và mã phiên bản đầu vào.
3. Nếu câu hỏi ghi BMI khác form, hiển thị hai giá trị và hỏi giá trị nào cần
   xét. Không âm thầm ghi đè form hoặc dùng giá trị cũ.
4. Tìm tài liệu và quy tắc có phạm vi áp dụng phù hợp.
5. Python thực hiện phép so sánh với mốc đã xác thực.
6. Backend dựng phần xác nhận đầu vào và kết quả đối chiếu. Gemini diễn giải
   kiến thức từ bằng chứng; các nhận định vẫn phải qua Safety.

Phân biệt ba loại dữ liệu:

| Loại | Ví dụ | Cách kiểm tra |
| --- | --- | --- |
| Người dùng cung cấp | BMI bằng 59 | Đối chiếu câu hỏi/form, ghi rõ chưa phải phép đo được xác minh |
| Kiến thức từ tài liệu | Một mốc phân loại BMI | Quote, URL, phạm vi áp dụng, phiên bản nguồn |
| Kết quả tính toán | So sánh giá trị đầu vào với mốc nguồn | Python tính, ghi ID quy tắc và hai đầu vào |

Không đưa mọi số trong câu hỏi vào danh sách số được phép dùng cho mọi
nhận định. Chỉ phần xác nhận đầu vào được dùng dữ liệu người dùng; kết luận
phải có quy tắc và bằng chứng tương ứng. Giữ kiểm tra số liệu hiện tại cho
claim do Gemini sinh. Phần tính toán có hợp đồng kiểm tra riêng và nguồn gốc rõ ràng.

**Nguồn bổ sung đầu tiên:** [NIDDK — Definition & Facts for Adult Overweight
& Obesity](https://www.niddk.nih.gov/health-information/weight-management/adult-overweight-obesity/definition-facts).
Bảng BMI này dành cho người từ 20 tuổi trở lên; có mốc 40 cho nhóm béo phì nặng.
Khi chưa biết tuổi, chỉ giải thích có điều kiện hoặc hỏi thêm. Mã `Age=1`
của form bao gồm 18–24 tuổi, nên không đủ để khẳng định người dùng đã từ 20 tuổi.

Với trẻ em, thai kỳ hoặc ngữ cảnh chưa có quy tắc phù hợp, không tự áp dụng
bảng người lớn. Không trộn ngưỡng đánh giá nguy cơ tiểu đường theo nhóm dân số
với ngưỡng phân loại BMI của một tài liệu khác.

Đề xuất lưu quy tắc có phiên bản trong `data/knowledge/clinical_rules.json`.
Mỗi quy tắc cần ID, thông số, đơn vị, điều kiện áp dụng, ranh giới bao gồm/không
bao gồm, nhãn kết quả, document/chunk nguồn, quote và dấu nội dung nguồn.
Quy tắc phải được rà soát với tài liệu; không cho LLM tự tạo mốc dùng trực tiếp.
Khi nguồn thay đổi hoặc không khớp, vô hiệu hóa quy tắc để kiểm tra lại.

**File dự kiến:** tạo `backend/knowledge/measurements.py` và
`backend/knowledge/clinical_rules.py`; mở rộng `backend/schemas/api.py`,
`backend/agents/nodes.py`, `backend/agents/safety.py` và state cần thiết.
Tên module cuối cùng có thể điều chỉnh khi triển khai để tránh trùng trách nhiệm.

**Đạt khi:** số 59 được nhắc lại đúng nguồn gốc; phép so sánh lấy mốc từ nguồn;
không kết luận tiểu đường từ BMI; câu thiếu tuổi có điều kiện rõ ràng; các câu
chứa số bịa hoặc tự đổi đơn vị vẫn bị chặn.

### A2. Kiểm tra ý nghĩa, bên cạnh kiểm tra trích dẫn

Lỗi cần xử lý đã quan sát trong giao diện: câu trả lời dẫn số liệu có trong
tài liệu nhưng gán khoảng tiền tiểu đường thành khoảng tiểu đường.

Giải pháp theo mức độ:

1. Với bảng ngưỡng đã có quy tắc: đối chiếu thông số, đơn vị, loại kết quả,
   ranh giới và phạm vi đối tượng bằng code.
2. Với nhận định thông thường: kiểm tra mâu thuẫn rõ ràng, dấu phủ định và
   tình trạng bằng chứng thiếu/khác ngữ cảnh. Không xem việc chứa cùng số là đủ.
3. Có thể thử bộ kiểm tra nghĩa bằng Gemini dưới cờ cấu hình, chỉ khi cần.
   Tối đa một lần rà soát và một lần sửa có giới hạn; nếu còn lỗi thì trả
   thông báo chưa xác minh được. Bộ kiểm tra LLM không phải người duyệt y khoa.
4. Ghi mã nguyên nhân trong trace để phân biệt thiếu nguồn, sai khoảng số,
   sai phạm vi, quota, timeout và lỗi JSON. Giao diện dùng lời giải thích dễ hiểu.

Giữ kết quả PyTorch hợp lệ khi phần diễn giải RAG lỗi. Không để một lỗi diễn
giải làm mất điểm mô hình đã tính thành công.

**File dự kiến:** `backend/rag/citation_validator.py`, module kiểm tra quy tắc,
`backend/agents/safety.py`, `backend/llm/llm_provider.py`,
`frontend/src/components/Answer.tsx` và evaluator liên quan.

**Đạt khi:** nhận định tráo hai nhóm kết quả bị phát hiện; quote đúng nhưng
diễn giải sai không được coi là đã chứng minh; API lỗi không tạo câu trả lời
hoặc trích dẫn giả; điểm ML đã hoàn tất vẫn được giữ.

### A3. Nút thử thay đổi và so sánh trước–sau

Học từ trang 24–25 của PDF, gắn vào trang dự đoán hiện có.

Giao diện có hồ sơ gốc và bản thử riêng. Cho sửa BMI và một số biến đã hỗ trợ;
hiện danh sách trường đã đổi, điểm trước/sau, chênh lệch điểm, lớp trước/sau
và ngưỡng. Nút “Áp dụng vào form” là hành động riêng; thử nghiệm không tự ghi đè gốc.

Backend nhận đủ 21 trường gốc và bản thay đổi đã xác thực. Chuẩn hóa bằng
cùng scaler, dùng cùng artifact và ngưỡng cho hai lần dự đoán. Không train lại.
Khi chưa đủ dữ liệu, trả danh sách trường thiếu thay vì điền ngầm.

Mỗi kết quả mang dấu đầu vào, phiên bản model và mã lần thử. Khi form đổi,
đánh dấu kết quả trước là cũ. Phản hồi đến muộn không được ghi đè kết quả của
bộ giá trị mới hơn.

**Endpoint đề xuất:** `POST /api/v1/scenarios`.
Đầu vào: hồ sơ gốc, thay đổi theo tên trường, dấu/phiên bản hồ sơ.
Đầu ra: kết quả gốc và bản thử, thay đổi đã áp dụng, chênh lệch điểm,
phiên bản model và dấu đầu vào. Giữ nguyên `/predict` và `/analyze`.

**File dự kiến:** tạo `backend/ml/scenarios.py`; mở rộng routes/schema;
thêm `frontend/src/components/ScenarioComparison.tsx` và sửa
`frontend/src/pages/Prediction.tsx`, service/type API.

**Đạt khi:** thay một trường giữ nguyên 20 trường khác; không đổi đầu vào thì
hai điểm khớp trong sai số số thực; hồ sơ gốc không bị sửa; BMI sai miền bị từ
chối; thao tác nhanh không gây lẫn phản hồi. Màn hình ghi rõ đây là thử hành vi
mô hình, không phải dự đoán hiệu quả điều trị hoặc mức giảm nguy cơ bệnh.

## 4. Đợt B — Làm rõ phần ML/DL và ngữ cảnh hồ sơ

### B1. Màn hình giải thích mô hình

Tách hai phần để tránh hiểu nhầm:

- **Ảnh hưởng chung:** đọc `artifacts/ml_feature_importance.json`, hiện bảng
  xếp hạng cùng model version, phương pháp và tập dữ liệu đã dùng. Đây là báo
  cáo phụ thuộc của mô hình, không phải mức nguy hiểm y khoa của từng biến.
- **Độ nhạy của hồ sơ hiện tại:** chọn thay đổi hợp lệ của một trường và chạy
  lại PyTorch. Hiện chính xác đầu vào nào đổi và điểm đổi bao nhiêu. Không
  gọi đây là đóng góp chính xác của đặc trưng vào điểm gốc.

Kiểm tra báo cáo thuộc đúng model; nếu thay model, không dùng lại biểu đồ cũ.
Không dùng kết quả xem trên test để tinh chỉnh model rồi vẫn coi cùng test là
đánh giá độc lập. SHAP có thể nghiên cứu sau nếu cần giải thích từng dự đoán;
chưa thêm dependency này vào MVP.

**Endpoint đề xuất:** `GET /api/v1/model-inspection` cho báo cáo chung.
Độ nhạy riêng tái sử dụng endpoint scenarios và giới hạn số lần thử.

**File dự kiến:** `backend/ml/inspection.py`, routes/schema, thành phần React
hiển thị báo cáo. Cách đo có thể đối chiếu [tài liệu permutation
importance](https://scikit-learn.org/stable/modules/permutation_importance.html).

### B2. So sánh Logistic Regression với MLP

Tận dụng hai artifact đã huấn luyện trên cùng cách chia dữ liệu.
Trước mắt không cần thêm Random Forest hoặc một mạng mới.

Hai mô hình nhận cùng 21 đặc trưng và đúng scaler đã dùng khi train.
Dịch vụ Logistic Regression phải lấy điểm của lớp 1 theo `classes_`, kiểm
tra số đặc trưng và nguồn gốc artifact. Bổ sung manifest gồm dấu model,
scaler, dataset và version để ràng buộc bộ artifact khi so sánh.

Ngưỡng hiện lưu: Logistic Regression khoảng 0,5890; MLP khoảng 0,6209.
Giữ ngưỡng tương ứng từng model, không ép cả hai về 0,5.
Không cộng điểm thành một tỷ lệ bệnh mới hoặc chọn model đúng chỉ vì điểm cao hơn.
Lựa chọn ngưỡng phải dựa trên dữ liệu dành riêng để chọn cấu hình, giữ tập test
cho đánh giá: [tài liệu về ngưỡng phân loại](https://scikit-learn.org/stable/modules/classification_threshold.html).

Giao diện hiện tên model, điểm, ngưỡng, lớp, version và trạng thái đồng ý/khác nhau.
Nếu một artifact lỗi, báo model đó không sẵn sàng và giữ kết quả model còn lại.

**Endpoint đề xuất:** `POST /api/v1/models/compare`.
**File dự kiến:** `backend/ml/comparison.py`, routes/schema và
`frontend/src/components/ModelComparison.tsx`.

**Đạt khi:** cùng input/scaler; ngưỡng đúng model; lặp lại kết quả ổn định;
thiếu artifact không sinh điểm giả; giao diện phân biệt điểm hồ sơ với metrics
đánh giá chung. Không so sánh trực tiếp số đo trong PDF với GlucoGuide để tuyên
bố model tốt hơn vì tập test và chính sách ngưỡng khác nhau.

### B3. Chat gắn với đúng hồ sơ

Học từ trang 11, 13, 24 và 28 của PDF. Cần có trước khi hỗ trợ tự nhiên
các câu như “Nếu giảm 3 thì sao?”.

MVP giữ một hồ sơ đang xét và lịch sử ngắn trong bộ nhớ phiên trình duyệt.
Tách hồ sơ gốc, bản thử và kết quả đã tính; không tự lưu thông tin sức khỏe
lâu dài. “Cuộc trò chuyện mới” phải làm rõ giữ hay bỏ hồ sơ liên quan.

Backend vẫn nhận dữ liệu cần thiết theo từng request. Mã phiên bản/dấu hồ sơ
được trả về để frontend đối chiếu. Không lưu hồ sơ người dùng trong đối tượng
workflow được cache dùng chung cho nhiều request.

Luồng hội thoại:

1. “BMI là gì?”: tra cứu, không yêu cầu đủ form.
2. “BMI của mình 59”: ghi nhận thông số cho câu hỏi, không tự dự đoán bằng
   cách điền nốt 20 trường.
3. “Dự đoán cho hồ sơ này”: chỉ chạy khi đủ 21 trường hợp lệ.
4. “Nếu BMI giảm 3”: tạo bản thử từ hồ sơ gốc đã xác định.
5. “Giảm 3 thì sao?”: chỉ suy ra BMI khi ngữ cảnh gần xác định rõ; nếu có
   nhiều khả năng thì hỏi lại.
6. “Bạn mình có BMI 30”: không sửa hồ sơ đang xét của người dùng.

Nếu dùng Gemini để nhận biết hành động, chỉ cho trả JSON theo schema các
hành động cho phép. Python kiểm tra trường và giới hạn trước khi gọi công cụ.
Không cho thực thi mã, Cypher hay SQL do LLM tự viết. Tiếp tục giữ 21 đặc trưng
ở phần xử lý backend; không tự gửi toàn bộ hồ sơ cho Gemini.

**File dự kiến:** một React context giữ hồ sơ phiên; Chat/Prediction/API types;
`backend/graph/state.py`, `backend/agents/nodes.py` và module nhận biết hành động.
Các trường API mới là tùy chọn để các request cũ tiếp tục chạy.

**Đạt khi:** hai phiên không trộn dữ liệu; câu nối tiếp dùng đúng hồ sơ;
thay đổi trong bản thử không sửa gốc; thiếu ngữ cảnh thì hỏi lại;
phản hồi cũ không gắn vào đầu vào mới.

## 5. Đợt C — Đưa GraphRAG và dữ liệu khảo sát vào trải nghiệm

### C1. Đồ thị Neo4j trong giao diện

MVP trước hết dùng dữ liệu từ `/retrieve`: thực thể, quan hệ, chunk và dấu
đã dùng trong context. Sau đó mở rộng endpoint đọc subgraph có giới hạn nếu cần.
Không trả toàn bộ database cho mỗi câu hỏi.

Hiển thị hai góc nhìn:

- Quan hệ giữa các khái niệm để người dùng đọc dễ hiểu.
- Đường chứng cứ `RelationFact → Evidence → Chunk → Document` khi mở chi tiết.

Bấm cạnh mở câu trích, URL, phạm vi/phủ định của quan hệ và snapshot.
Phân biệt quan hệ được truy xuất với quan hệ thực sự hỗ trợ nguồn trong context.
Đường hai bước chỉ giúp tìm bằng chứng, không tự tạo kết luận nhân quả mới.

Tất cả truy vấn đi qua FastAPI, dùng Cypher có tham số và ràng buộc snapshot.
Không đưa mật khẩu hoặc kết nối Bolt vào frontend. Neo4j lỗi thì báo trạng thái
không khả dụng, không dựng đồ thị giả. Chat vẫn dùng fallback đã được thiết kế.

**File dự kiến:** mở rộng `backend/api/routes.py` và bộ đọc Neo4j khi cần;
thêm `frontend/src/components/KnowledgeGraph.tsx`, các type graph.
Đồ thị nhỏ có thể bắt đầu bằng SVG; cân nhắc React Flow cho thao tác bấm/kéo
thay vì đầu tư sân khấu 3D ngay.

**Đạt khi:** mọi cạnh mở được chứng cứ thuộc cùng snapshot; quan hệ phủ định
không bị đảo nghĩa; không lộ thông tin kết nối; không truy vấn không giới hạn.

### C2. Thống kê từ dữ liệu CDC

Đây là khả năng mới, tách khỏi dự đoán cá nhân và RAG tài liệu.
Ví dụ: “Trong dữ liệu khảo sát, nhóm BMI này có bao nhiêu hồ sơ?” hoặc
“Trong nhóm tuổi đã chọn, nhãn 0 và nhãn 1 phân bố thế nào?”.

Bắt đầu bằng các bộ lọc và phép thống kê định sẵn trên bản dữ liệu có dấu
nguồn gốc, dùng Pandas đang có. Chưa cần SQLite để chỉ đếm/lọc.
Nếu cần truy vấn nhiều hoặc lưu phiên về sau, mới đánh giá SQLite.
Không nhận SQL tự do do người dùng/LLM cung cấp.

Mỗi kết quả phải ghi điều kiện lọc, số mẫu, nguồn CSV, cách làm sạch và nhãn
đang dùng. Phân biệt nhãn khảo sát thật với lớp do model dự đoán.
Tỷ lệ của một nhóm trong dữ liệu không được diễn giải thành xác suất mắc bệnh
của người đang nhập form.

**Endpoint đề xuất:** `POST /api/v1/dataset/query` với schema bộ lọc cho phép.
**Đạt khi:** số đếm đối chiếu được bằng Pandas; nhóm rỗng được xử lý rõ;
mã tuổi/giới tính đúng từ điển; không nhầm nhãn với dự đoán.

### C3. Tiến trình agent trực tiếp và chế độ demo giới hạn

Giữ trace hiện tại làm nền tảng. Có thể bổ sung stream sự kiện gồm request ID,
thứ tự, tên bước, trạng thái và thời gian do backend đo. Giao diện nhận sự kiện
để hiện đang dự đoán, truy xuất, soạn câu hoặc kiểm tra.

Sự kiện chỉ phản ánh thực thi công cụ, không hiển thị suy nghĩ nội bộ của LLM.
Xử lý ngắt kết nối, loại trùng, phản hồi cuối và hết thời gian chờ.
Nếu chưa cần SSE, giữ request thông thường và trace sau khi hoàn tất;
không dựng thanh tiến trình giả rồi mô tả là sự kiện thật.
Tham khảo [FastAPI StreamingResponse](https://fastapi.tiangolo.com/advanced/custom-response/).

Demo khi Gemini không khả dụng vẫn có thể chạy `/predict`, thử thay đổi và
so sánh model. Tra cứu offline có thể thử dùng chỉ mục từ khóa đã có, được
gắn nhãn riêng và đánh giá riêng; hiển thị đoạn nguồn thay vì giả là câu trả
lời Gemini. Không tự bật BM25/reranker cho luồng chính khi chưa qua đánh giá.

## 6. Cập nhật dữ liệu mà vẫn giữ chỉ mục an toàn

1. Tải nguồn BMI mới, giữ bản gốc và metadata URL, thời điểm, checksum.
2. Kiểm tra loader, bảng, đơn vị, heading và chunk trước khi gọi embedding.
3. Index bằng bộ lọc `--document-id`; các tài liệu không đổi được bỏ qua.
4. Bổ sung quan hệ BMI có quote thật nếu cần đưa kiến thức mới vào graph.
   Không tự gắn mọi chunk mới thành một quan hệ y khoa.
5. Xây bundle snapshot mới từ corpus hiện tại, dùng lại vector đã có;
   migration và kiểm chứng Neo4j thành công mới chuyển active snapshot.
6. Nếu cần đánh giá trước khi chuyển, dùng collection/snapshot ứng viên riêng.
   Chỉ giữ con trỏ snapshot cũ là chưa đủ cho rollback nếu collection gốc đã
   bị thay đổi. Giữ bundle/collection cũ tương thích hoặc kế hoạch khôi phục.
7. Đo lại bộ truy xuất gốc và các câu mới. Báo riêng corpus cũ/mới;
   các số 58 chunk và 36 quan hệ trong báo cáo cũ là số lịch sử.

Không xóa toàn bộ ChromaDB hoặc Neo4j. Không tạo lại embedding cho nguồn không đổi.
Chỉ thay chỉ mục khi đã có đủ vector và dữ liệu sạch.

## 7. Hợp đồng API và thứ tự phụ thuộc

Tên endpoint dưới đây là đề xuất, chưa tồn tại trừ các endpoint ghi ở mục 2.

| Bổ sung | Trách nhiệm | Phụ thuộc |
| --- | --- | --- |
| `/scenarios` | Chạy trước–sau từ cùng hồ sơ và model | Xác thực 21 đầu vào, dấu hồ sơ |
| `/model-inspection` | Đọc báo cáo ảnh hưởng chung đúng model | Artifact inspection có nguồn gốc |
| `/models/compare` | So sánh LR và MLP theo ngưỡng riêng | Dịch vụ LR và kiểm tra artifact |
| Ngữ cảnh tùy chọn của `/chat` hoặc `/analyze` | Gắn câu nối tiếp với hồ sơ | Quản lý hồ sơ phiên, nhận biết hành động |
| Đọc subgraph nếu cần | Nút, cạnh và chứng cứ có giới hạn | Neo4j/snapshot và type frontend |
| `/dataset/query` | Thống kê theo bộ lọc cho phép | DatasetService với schema cố định |
| Endpoint stream nếu cần | Sự kiện thực thi thật | Giao thức sự kiện và quản lý request |

Các trường cũ của `PredictionResult` và `AnalysisResponse` giữ ý nghĩa hiện tại.
Bổ sung dữ liệu theo trường tùy chọn hoặc endpoint riêng. Đồng bộ Pydantic,
TypeScript và OpenAPI. Lỗi dữ liệu tiếp tục trả 422; lỗi dịch vụ và fallback
cần mã nguyên nhân rõ ràng, tương thích hành vi hiện có.

## 8. Kiểm thử và tiêu chí nghiệm thu

Các tiêu chí dưới đây là **mục tiêu cần kiểm chứng**, không phải kết quả đã chạy.

| Nhóm | Ca bắt buộc |
| --- | --- |
| Thông số người dùng | BMI nguyên/thập phân/dấu phẩy; số không hợp lệ; nhiều người; số câu hỏi khác form; thiếu tuổi |
| Quy tắc | Ranh giới dưới/trên/bằng mốc; đơn vị; nguồn đổi; quy tắc ngoài phạm vi; tráo nhãn hai khoảng |
| ML | Cùng đầu vào cho cùng kết quả; đúng scaler; đúng ngưỡng từng model; thiếu artifact; input giữ nguyên |
| Mô phỏng | Đúng trường đổi; không sửa gốc; sai miền; nhiều request đến không theo thứ tự |
| Hồ sơ | Hai phiên riêng; câu nối tiếp thiếu ngữ cảnh; câu về người khác; kết quả cũ và phiên bản mới |
| Graph | Truy vấn có giới hạn/tham số; đúng snapshot; cạnh có nguồn; phủ định; Neo4j mất kết nối |
| RAG | Quote giả; ID lạ; số y khoa bịa; nhầm nhóm xét nghiệm; prompt injection; quota/timeout |
| Giao diện | Nguồn mở đúng; gắn kết quả đúng input; lỗi một nhánh giữ nhánh khác; nhãn điểm không thành xác suất |

Thêm một nhóm câu có số đầu vào và câu nối tiếp vào bộ đánh giá. Giữ bộ
truy xuất cũ để đo hồi quy. Khi nguồn thay đổi, lưu phiên bản corpus và bộ câu
đánh giá tương ứng; không chỉnh annotation theo output để làm tăng chỉ số.

Kiểm thử rule/API được mock Gemini và dùng dữ liệu mẫu rõ ràng. Neo4j tích hợp
chạy database thật trên snapshot test tách biệt. Demo đầu-cuối gọi Gemini thật
chỉ khi có key/quota, ghi thời điểm/model/corpus; không coi mock là bằng chứng
về chất lượng câu trả lời. Đánh giá nghĩa cần người đọc đối chiếu với nguồn.

Hoàn tất mỗi phần thì chạy kiểm thử liên quan. Khi ghép các phần, chạy lại
toàn bộ backend, build frontend và các luồng Playwright thực sự thay đổi.

## 9. Thứ tự bàn giao

1. **Bản A1:** dữ liệu BMI sạch, quy tắc có nguồn, tách số đầu vào và hồi quy
   lỗi diễn giải ngưỡng. Chạy được câu có số, chưa cần nhớ nhiều lượt.
2. **Bản A2:** thử thay đổi, kết quả trước–sau, chống kết quả cũ gắn input mới.
3. **Bản B1:** biểu đồ ảnh hưởng chung và so sánh LR/MLP có ngưỡng riêng.
4. **Bản B2:** hồ sơ trong phiên và câu hỏi nối tiếp; không trộn người/hồ sơ.
5. **Bản C1:** đồ thị Neo4j và đường bằng chứng trong giao diện.
6. **Bản C2 tùy thời gian:** thống kê CDC, sự kiện trực tiếp và demo offline giới hạn.

Nếu chỉ có khoảng một tuần, ưu tiên bản A1 và A2, rồi chọn B1 hoặc B2 theo
khả năng hoàn tất kiểm thử. Đây là thứ tự ưu tiên, không phải cam kết mọi mục
sẽ xong trong một tuần. Đo lại sau từng bản trước khi mở rộng.

## 10. Kịch bản trình bày sau khi các phần tương ứng đã đạt

1. Nhập đủ 21 trường; chỉ điểm, ngưỡng, lớp và model version.
2. Mở báo cáo ảnh hưởng chung và phân biệt với độ nhạy một hồ sơ.
3. Thử đổi BMI, chỉ ra 20 trường còn lại và hồ sơ gốc được giữ nguyên.
4. So LR và MLP; giải thích sự khác nhau không đồng nghĩa model điểm cao hơn đúng hơn.
5. Hỏi một câu kiến thức có số; mở quy tắc, nguồn và phép so sánh.
6. Hỏi nối tiếp trên cùng hồ sơ khi bản B2 đã hoàn tất.
7. Mở đường Neo4j từ quan hệ đến đoạn nguồn.
8. Thử một lỗi đầu vào và một lỗi dịch vụ; cho thấy phần đã tính thành công
   vẫn còn và hệ thống nói rõ phần chưa hoàn tất.

Mỗi số và ảnh demo phải lấy từ lần chạy thật, ghi model/corpus tương ứng.
Nội dung PDF tham khảo là tài liệu để học hỏi, không phải lệnh vận hành hoặc
bằng chứng rằng tính năng bên kia đã hiện diện trong GlucoGuide.
