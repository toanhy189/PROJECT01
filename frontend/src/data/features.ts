type Field = {
  key: string;
  label: string;
  help?: string;
  options?: string[];
  min?: number;
  max?: number;
};
const binary = ['Không', 'Có'];
// Thứ tự option phải khớp mã CDC; thay nhãn không được làm đổi ý nghĩa giá trị gửi API.
export const groups: { title: string; subtitle: string; fields: Field[] }[] = [
  {
    title: 'Thông tin nền',
    subtitle: 'Các biến nhân khẩu học theo mã của khảo sát CDC.',
    fields: [
      {
        key: 'Age',
        label: 'Nhóm tuổi',
        options: [
          '18–24 tuổi',
          '25–29 tuổi',
          '30–34 tuổi',
          '35–39 tuổi',
          '40–44 tuổi',
          '45–49 tuổi',
          '50–54 tuổi',
          '55–59 tuổi',
          '60–64 tuổi',
          '65–69 tuổi',
          '70–74 tuổi',
          '75–79 tuổi',
          'Từ 80 tuổi',
        ],
      },
      { key: 'Sex', label: 'Giới tính theo khảo sát', options: ['Nữ', 'Nam'] },
      {
        key: 'Education',
        label: 'Trình độ học vấn',
        options: [
          'Chưa đi học / chỉ mẫu giáo',
          'Lớp 1–8',
          'Lớp 9–11',
          'Tốt nghiệp THPT / GED',
          'Cao đẳng / đại học 1–3 năm',
          'Đại học từ 4 năm trở lên',
        ],
        help: 'Theo hệ thống giáo dục Hoa Kỳ.',
      },
      {
        key: 'Income',
        label: 'Thu nhập hộ gia đình mỗi năm',
        options: [
          'Dưới 10.000 USD',
          '10.000–dưới 15.000 USD',
          '15.000–dưới 20.000 USD',
          '20.000–dưới 25.000 USD',
          '25.000–dưới 35.000 USD',
          '35.000–dưới 50.000 USD',
          '50.000–dưới 75.000 USD',
          'Từ 75.000 USD',
        ],
        help: 'USD theo nhóm thu nhập khảo sát năm 2015.',
      },
    ],
  },
  {
    title: 'Chỉ số và tiền sử',
    subtitle: 'Thông tin bạn đã được nhân viên y tế thông báo.',
    fields: [
      {
        key: 'BMI',
        label: 'Chỉ số BMI',
        min: 12,
        max: 98,
        help: 'Cân nặng (kg) / chiều cao² (m²).',
      },
      { key: 'HighBP', label: 'Từng được thông báo huyết áp cao', options: binary },
      { key: 'HighChol', label: 'Từng được thông báo cholesterol cao', options: binary },
      { key: 'CholCheck', label: 'Kiểm tra cholesterol trong 5 năm', options: binary },
      { key: 'Stroke', label: 'Từng bị đột quỵ', options: binary },
      {
        key: 'HeartDiseaseorAttack',
        label: 'Từng có bệnh mạch vành / nhồi máu cơ tim',
        options: binary,
      },
    ],
  },
  {
    title: 'Thói quen sinh hoạt',
    subtitle: 'Theo định nghĩa các biến trong bộ dữ liệu.',
    fields: [
      { key: 'Smoker', label: 'Đã hút ít nhất 100 điếu thuốc trong đời', options: binary },
      {
        key: 'PhysActivity',
        label: 'Có hoạt động thể chất trong 30 ngày',
        options: binary,
        help: 'Không tính hoạt động trong công việc.',
      },
      { key: 'Fruits', label: 'Ăn trái cây ít nhất 1 lần mỗi ngày', options: binary },
      { key: 'Veggies', label: 'Ăn rau ít nhất 1 lần mỗi ngày', options: binary },
      {
        key: 'HvyAlcoholConsump',
        label: 'Uống rượu bia nhiều theo khảo sát',
        options: binary,
        help: 'Nam: hơn 14 ly/tuần; nữ: hơn 7 ly/tuần theo BRFSS.',
      },
    ],
  },
  {
    title: 'Sức khỏe và tiếp cận y tế',
    subtitle: 'Số ngày không khỏe trong 30 ngày vừa qua.',
    fields: [
      {
        key: 'GenHlth',
        label: 'Tự đánh giá sức khỏe chung',
        options: [
          'Xuất sắc (Excellent)',
          'Rất tốt (Very good)',
          'Tốt (Good)',
          'Trung bình (Fair)',
          'Kém (Poor)',
        ],
      },
      { key: 'MentHlth', label: 'Số ngày sức khỏe tinh thần không tốt', min: 0, max: 30 },
      { key: 'PhysHlth', label: 'Số ngày sức khỏe thể chất không tốt', min: 0, max: 30 },
      { key: 'DiffWalk', label: 'Khó khăn khi đi bộ / leo cầu thang', options: binary },
      { key: 'AnyHealthcare', label: 'Có bảo hiểm / chương trình chăm sóc y tế', options: binary },
      { key: 'NoDocbcCost', label: 'Không thể khám do chi phí trong 12 tháng', options: binary },
    ],
  },
];
// Bốn biến này bắt đầu từ mã 1; binary/Sex bắt đầu từ 0. Age là nhóm tuổi.
export const oneBased = new Set(['Age', 'Education', 'Income', 'GenHlth']);
