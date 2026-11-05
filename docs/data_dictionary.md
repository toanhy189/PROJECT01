# Ánh xạ 21 đặc trưng

Nguồn đối chiếu: [bộ dữ liệu UCI](https://archive.ics.uci.edu/dataset/891/cdc+diabetes+health+indicators),
[CDC BRFSS 2015 và codebook](https://www.cdc.gov/brfss/annual_data/annual_2015.html).
CSV đã được đọc và kiểm tra miền; frontend ánh xạ theo mã dưới đây, backend kiểm tra
kiểu và miền nghiêm ngặt. JSON binary/categorical phải là số nguyên, không nhận string/bool.
Đã đối chiếu với `backend/schemas/features.py`, form giao diện và
`artifacts/data_report.json` ngày **03/11/2026**; thứ tự bảng là thứ tự 21 đầu vào mô hình.

| Trường | Ý nghĩa | Mã/miền |
| --- | --- | --- |
| HighBP | Được thông báo huyết áp cao | 0 không, 1 có |
| HighChol | Được thông báo cholesterol cao | 0 không, 1 có |
| CholCheck | Kiểm tra cholesterol trong 5 năm | 0 không, 1 có |
| BMI | Chỉ số khối cơ thể, kg/m² | CSV thực tế 12–98; API nhận số hữu hạn trong miền |
| Smoker | Từng hút ít nhất 100 điếu trong đời | 0 không, 1 có |
| Stroke | Từng được thông báo đột quỵ | 0 không, 1 có |
| HeartDiseaseorAttack | Bệnh mạch vành / nhồi máu cơ tim | 0 không, 1 có |
| PhysActivity | Hoạt động thể chất 30 ngày, ngoài công việc | 0 không, 1 có |
| Fruits | Ăn trái cây ít nhất một lần/ngày | 0 không, 1 có |
| Veggies | Ăn rau ít nhất một lần/ngày | 0 không, 1 có |
| HvyAlcoholConsump | Uống nhiều, nam >14 ly/tuần, nữ >7 ly/tuần theo định nghĩa khảo sát | 0 không, 1 có |
| AnyHealthcare | Có bảo hiểm / chương trình chăm sóc y tế | 0 không, 1 có |
| NoDocbcCost | Cần khám nhưng không thể do chi phí trong 12 tháng | 0 không, 1 có |
| GenHlth | Tự đánh giá sức khỏe chung | 1 xuất sắc, 2 rất tốt, 3 tốt, 4 trung bình, 5 kém |
| MentHlth | Số ngày sức khỏe tinh thần không tốt trong 30 ngày | Số nguyên 0–30 |
| PhysHlth | Số ngày sức khỏe thể chất không tốt trong 30 ngày | Số nguyên 0–30 |
| DiffWalk | Khó đi bộ / leo cầu thang | 0 không, 1 có |
| Sex | Giới tính theo mã khảo sát | 0 nữ, 1 nam |
| Age | Nhóm tuổi, không phải tuổi thật | 1–13 theo bảng dưới |
| Education | Trình độ học vấn theo hệ Hoa Kỳ | 1–6 theo bảng dưới |
| Income | Thu nhập hộ gia đình/năm theo USD năm khảo sát | 1–8 theo bảng dưới |

## Age

| Mã | Nhóm tuổi | Mã | Nhóm tuổi |
| --- | --- | --- | --- |
| 1 | 18–24 | 8 | 55–59 |
| 2 | 25–29 | 9 | 60–64 |
| 3 | 30–34 | 10 | 65–69 |
| 4 | 35–39 | 11 | 70–74 |
| 5 | 40–44 | 12 | 75–79 |
| 6 | 45–49 | 13 | Từ 80 |
| 7 | 50–54 | | |

## Education

| Mã | Ý nghĩa |
| --- | --- |
| 1 | Chưa đi học / chỉ mẫu giáo |
| 2 | Lớp 1–8 |
| 3 | Lớp 9–11 |
| 4 | Lớp 12 / GED |
| 5 | Cao đẳng / đại học 1–3 năm |
| 6 | Đại học từ 4 năm trở lên |

## Income

| Mã | USD/năm |
| --- | --- |
| 1 | Dưới 10.000 |
| 2 | 10.000 đến dưới 15.000 |
| 3 | 15.000 đến dưới 20.000 |
| 4 | 20.000 đến dưới 25.000 |
| 5 | 25.000 đến dưới 35.000 |
| 6 | 35.000 đến dưới 50.000 |
| 7 | 50.000 đến dưới 75.000 |
| 8 | Từ 75.000 |

Không tự đổi tiền VND sang mã thu nhập: đây là biến xã hội kinh tế trong khảo sát
Hoa Kỳ, không có tính tương đương tự động giữa quốc gia/thời điểm. Nếu không biết
thông tin, không đoán mã; MVP yêu cầu đủ 21 trường và không có mã unknown.

Target `Diabetes_binary`: 0 không tiểu đường; 1 tiền tiểu đường hoặc tiểu đường theo
nhãn dữ liệu. Không thêm target vào payload suy luận. CSV UCI đang lưu được Pandas
đọc thành `int64` ở tất cả 22 cột; một bản CSV khác có thể lưu mã nguyên dưới dạng
float, nên loader kiểm tra giá trị nguyên thay vì chỉ dựa vào kiểu cột. Frontend
gửi categorical dạng integer; API cho phép BMI là số hữu hạn trong khoảng 12–98,
kể cả số thập phân. Pipeline train yêu cầu giá trị nguyên ở cả cột BMI theo CSV CDC.
