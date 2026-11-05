/** Khung điều hướng và trạng thái kết nối API của ứng dụng local. */
import { useEffect, useState } from 'react';
import {
  Activity,
  BookOpen,
  ChevronRight,
  CircleHelp,
  HeartPulse,
  LayoutDashboard,
  Menu,
  ShieldCheck,
  X,
} from 'lucide-react';
import Dashboard from './pages/Dashboard';
import Prediction from './pages/Prediction';
import Chat from './pages/Chat';
import { api } from './services/api';
import type { ModelInfo } from './types/api';
import { ProfileProvider } from './state/ProfileContext';

type Page = 'dashboard' | 'prediction' | 'chat';
const navigation = [
  { id: 'dashboard' as const, label: 'Tổng quan', icon: LayoutDashboard },
  { id: 'prediction' as const, label: 'Phân loại chỉ số', icon: Activity },
  { id: 'chat' as const, label: 'Trợ lý kiến thức', icon: BookOpen },
];

/** Chuyển giữa ba trang; không lưu thông tin sức khỏe vào bộ nhớ trình duyệt bền vững. */
function AppShell() {
  const [page, setPage] = useState<Page>('dashboard');
  const [menu, setMenu] = useState(false);
  const [connected, setConnected] = useState<boolean | null>(null);
  const [model, setModel] = useState<ModelInfo | null>(null);
  const [help, setHelp] = useState(false);
  useEffect(() => {
    // Bỏ qua response về muộn sau khi component bị tháo, kể cả khi StrictMode chạy lại effect.
    let active = true;
    void api
      .health()
      .then(() => {
        if (active) setConnected(true);
      })
      .catch(() => {
        if (active) setConnected(false);
      });
    void api
      .modelInfo()
      .then((value) => {
        if (active) setModel(value);
      })
      .catch(() => {
        if (active) setModel(null);
      });
    return () => {
      active = false;
    };
  }, []);
  /** Đóng menu di động và đưa người dùng về đầu trang vừa chọn. */
  function navigate(next: Page) {
    setPage(next);
    setMenu(false);
    window.scrollTo({ top: 0 });
  }
  return (
    <div className="app-shell">
      {menu && (
        <button className="sidebar-overlay" aria-label="Đóng menu" onClick={() => setMenu(false)} />
      )}
      <aside className={`sidebar ${menu ? 'open' : ''}`}>
        <a
          href="#"
          className="brand"
          onClick={(event) => {
            event.preventDefault();
            navigate('dashboard');
          }}
        >
          <span className="brand-symbol">
            <HeartPulse size={25} strokeWidth={1.7} />
          </span>
          <div>
            GlucoGuide<small>Hiểu để chủ động hơn.</small>
          </div>
        </a>
        <span className="nav-caption">KHÔNG GIAN LÀM VIỆC</span>
        <nav aria-label="Điều hướng chính">
          {navigation.map((item) => (
            <button
              key={item.id}
              className={page === item.id ? 'nav-item active' : 'nav-item'}
              aria-current={page === item.id ? 'page' : undefined}
              onClick={() => navigate(item.id)}
            >
              <item.icon size={19} />
              <span>{item.label}</span>
              {page === item.id && <span className="nav-active-dot" />}
            </button>
          ))}
        </nav>
        <div className="sidebar-bottom">
          <div className="sidebar-note">
            <ShieldCheck size={21} />
            <strong>
              Kiến thức có giới hạn.
              <br />
              Sức khỏe cần chuyên gia.
            </strong>
            <p>Kết quả chỉ hỗ trợ tìm hiểu, không dùng làm chẩn đoán.</p>
          </div>
          <div className="project-signature">
            <span>ĐA</span>
            <div>
              Đồ án đại học<small>Diabetes Multi-Agent · v1.0</small>
            </div>
          </div>
        </div>
      </aside>
      <div className="main-shell">
        <header className="topbar">
          <div className="breadcrumbs">
            <button
              className="mobile-menu icon-button"
              aria-label="Mở menu"
              onClick={() => setMenu(!menu)}
            >
              <Menu size={20} />
            </button>
            <span>Không gian sức khỏe</span>
            <ChevronRight size={14} />
            <strong>{navigation.find((item) => item.id === page)?.label}</strong>
          </div>
          <div className="topbar-actions">
            <span className={`connection-status ${connected ? 'online' : ''}`}>
              <i />
              {connected === null
                ? 'Đang kết nối…'
                : connected
                  ? 'API sẵn sàng'
                  : 'API chưa kết nối'}
            </span>
            <button
              className="icon-button"
              aria-label="Thông tin hệ thống"
              onClick={() => setHelp(!help)}
            >
              {help ? <X size={19} /> : <CircleHelp size={19} />}
            </button>
          </div>
        </header>
        {help && (
          <div className="help-banner">
            <strong>Trạng thái hệ thống</strong>
            <p>
              {model?.ready
                ? `Mô hình: ${model.model_version}.`
                : 'Chưa tải được mô hình; kiểm tra backend và artifacts.'}{' '}
              RAG cần GEMINI_API_KEY và chỉ mục ChromaDB.
            </p>
          </div>
        )}
        <main className="page-content">
          {page === 'dashboard' ? (
            <Dashboard navigate={navigate} />
          ) : page === 'prediction' ? (
            <Prediction />
          ) : (
            <Chat />
          )}
          <footer className="page-footer">
            <span>GlucoGuide · Nghiên cứu để hiểu hơn</span>
            <span>
              <ShieldCheck size={12} /> Không thay thế tư vấn y khoa
            </span>
          </footer>
        </main>
      </div>
    </div>
  );
}

/** Giữ form khi đổi trang, toàn bộ dữ liệu biến mất khi đóng hoặc tải lại tab. */
export default function App() {
  return (
    <ProfileProvider>
      <AppShell />
    </ProfileProvider>
  );
}
