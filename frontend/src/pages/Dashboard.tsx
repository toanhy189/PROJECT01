/** Trang giới thiệu phạm vi, kiến trúc và hai chức năng chính của MVP. */
import {
  ArrowRight,
  Activity,
  BookOpen,
  Layers3,
  MoveUpRight,
  ShieldCheck,
  Workflow,
  Cpu,
  Database,
  Sparkles,
} from 'lucide-react';
import DatasetExplorer from '../components/DatasetExplorer';

/** Các con số mô tả đặc tả hệ thống, không phải metrics hoặc trạng thái dịch vụ giả. */
export default function Dashboard({
  navigate,
}: {
  navigate: (page: 'prediction' | 'chat') => void;
}) {
  return (
    <>
      <div className="page-heading">
        <div>
          <p className="eyebrow">KHÔNG GIAN KIẾN THỨC SỨC KHỎE</p>
          <h1>Hiểu chỉ số. Hiểu sức khỏe.</h1>
          <p>Một góc nhìn có cơ sở, để bạn chủ động tìm hiểu về tiểu đường.</p>
        </div>
        <span className="academic-badge">
          <Layers3 size={14} /> Đồ án nghiên cứu · MVP
        </span>
      </div>
      <section className="hero">
        <div className="hero-copy">
          <span className="hero-label">
            <i /> AI ĐỒNG HÀNH CÙNG KIẾN THỨC
          </span>
          <h2>
            Từ dữ liệu đến
            <br />
            <em>sự thấu hiểu.</em>
          </h2>
          <p>
            Khám phá các chỉ số sức khỏe bằng mô hình học sâu và tìm câu trả lời từ tài liệu NIDDK
            có trích dẫn nguồn.
          </p>
          <button className="button button-light" onClick={() => navigate('prediction')}>
            Bắt đầu phân loại <ArrowRight size={17} />
          </button>
          <small>
            <ShieldCheck size={14} /> Công cụ học thuật, không thay thế chẩn đoán y khoa
          </small>
        </div>
        <div className="hero-art" aria-hidden="true">
          <div className="orbit orbit-one" />
          <div className="orbit orbit-two" />
          <div className="orbit orbit-three" />
          <div className="art-center">
            <Activity size={56} strokeWidth={1.2} />
          </div>
          <div className="art-label art-label-one">
            <Cpu size={18} />
            <div>
              Deep Learning<small>PyTorch MLP</small>
            </div>
          </div>
          <div className="art-label art-label-two">
            <BookOpen size={18} />
            <div>
              Kiến thức có nguồn<small>Custom RAG</small>
            </div>
          </div>
          <span className="orbit-node node-a" />
          <span className="orbit-node node-b" />
          <span className="art-caption">DỮ LIỆU · TRI THỨC · KẾT NỐI</span>
        </div>
      </section>
      <div className="overview-stats">
        <div>
          <span className="stat-icon mint">
            <Activity size={21} />
          </span>
          <section>
            <strong>
              21 <small>đặc trưng</small>
            </strong>
            <p>Chỉ số khảo sát CDC</p>
          </section>
        </div>
        <div>
          <span className="stat-icon sand">
            <Workflow size={21} />
          </span>
          <section>
            <strong>
              4 <small>Agent chuyên trách</small>
            </strong>
            <p>Điều phối bằng LangGraph</p>
          </section>
        </div>
        <div>
          <span className="stat-icon blue">
            <Database size={21} />
          </span>
          <section>
            <strong>
              2015 <small>BRFSS</small>
            </strong>
            <p>Dữ liệu khảo sát tại Hoa Kỳ</p>
          </section>
        </div>
      </div>
      <div className="section-heading">
        <h2>Bạn muốn bắt đầu từ đâu?</h2>
        <span>Hai cách để khám phá</span>
      </div>
      <div className="action-grid">
        {[
          {
            page: 'prediction' as const,
            icon: Activity,
            color: 'mint',
            eyebrow: '01 / PHÂN LOẠI CHỈ SỐ',
            title: 'Lắng nghe dữ liệu của bạn',
            description:
              'Nhập 21 đặc trưng để xem điểm và lớp dự đoán theo định nghĩa của bộ dữ liệu CDC.',
            action: 'Mở bảng thông tin',
          },
          {
            page: 'chat' as const,
            icon: BookOpen,
            color: 'sand',
            eyebrow: '02 / TRỢ LÝ KIẾN THỨC',
            title: 'Hỏi để hiểu rõ hơn',
            description:
              'Tra cứu kiến thức tiểu đường từ kho tài liệu, với bằng chứng và đường dẫn nguồn để đối chiếu.',
            action: 'Bắt đầu cuộc trò chuyện',
          },
        ].map((item) => (
          <button className="action-card" key={item.page} onClick={() => navigate(item.page)}>
            <div className="action-card-top">
              <span className={`feature-icon ${item.color}`}>
                <item.icon size={24} />
              </span>
              <MoveUpRight size={20} />
            </div>
            <span className="eyebrow">{item.eyebrow}</span>
            <h3>{item.title}</h3>
            <p>{item.description}</p>
            <span className="card-link">
              {item.action}
              <ArrowRight size={16} />
            </span>
          </button>
        ))}
      </div>
      <section className="method-strip">
        <div className="method-title">
          <Sparkles size={19} />
          <div>
            <h3>Cách GlucoGuide kết nối thông tin</h3>
            <p>Mỗi bước có vai trò rõ ràng và có thể kiểm tra.</p>
          </div>
        </div>
        <div className="method-flow">
          <span>Thông tin đầu vào</span>
          <ArrowRight size={14} />
          <span>Coordinator</span>
          <ArrowRight size={14} />
          <span>Agent chuyên trách</span>
          <ArrowRight size={14} />
          <span>Kiểm tra an toàn</span>
        </div>
      </section>
      <DatasetExplorer />
      <div className="scope-note">
        <ShieldCheck size={20} />
        <div>
          <strong>Một điểm mô hình không phải một chẩn đoán.</strong>
          <p>
            Lớp 1 gộp tiền tiểu đường và tiểu đường theo nhãn khảo sát. Kết quả không phải xác suất
            mắc bệnh trong tương lai. Hãy trao đổi với bác sĩ khi cần đánh giá sức khỏe.
          </p>
        </div>
      </div>
    </>
  );
}
