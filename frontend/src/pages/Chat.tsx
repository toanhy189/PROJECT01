/** Hỏi đáp RAG độc lập từng câu, kèm nguồn và trace của lần xử lý gần nhất. */
import { useState, type FormEvent } from 'react';
import { ArrowUp, BookOpen, LoaderCircle, MessageCircle, Plus, Sparkles } from 'lucide-react';
import AgentTrace from '../components/AgentTrace';
import Answer from '../components/Answer';
import KnowledgeGraph from '../components/KnowledgeGraph';
import { api } from '../services/api';
import { useProfile } from '../state/ProfileContext';

const suggestions = [
  'Tiểu đường là gì?',
  'Những yếu tố nào liên quan đến tiểu đường típ 2?',
  'Có những xét nghiệm nào để chẩn đoán tiểu đường?',
];

/** Lưu lịch sử hiển thị trong state; không gửi lịch sử chat cũ làm context cho backend. */
export default function Chat() {
  const [query, setQuery] = useState('');
  const { messages, setMessages, features, shareProfile, setShareProfile } = useProfile();
  const [loading, setLoading] = useState(false);
  const latest = [...messages].reverse().find((message) => message.result)?.result ?? null;
  /** Gửi một câu hỏi và cập nhật đúng lượt đang chờ khi nhận response hoặc lỗi. */
  async function send(question: string) {
    // Khóa gửi khi đang chờ để response không bị gắn nhầm vào một lượt chat mới hơn.
    if (!question.trim() || loading) return;
    setQuery('');
    setLoading(true);
    const id = crypto.randomUUID();
    const previous = messages.at(-1);
    const focus =
      previous &&
      (/\bbmi\b/i.test(previous.question) ||
        previous.result?.scenario_result ||
        previous.result?.measurement_result)
        ? ('BMI' as const)
        : undefined;
    setMessages((previous) => [...previous, { id, question }]);
    try {
      const result = await api.chat(
        question,
        shareProfile && features ? features : undefined,
        focus,
      );
      setMessages((previous) =>
        previous.map((message) => (message.id === id ? { ...message, result } : message)),
      );
    } catch (cause) {
      setMessages((previous) =>
        previous.map((message) =>
          message.id === id
            ? { ...message, error: cause instanceof Error ? cause.message : 'Có lỗi xử lý.' }
            : message,
        ),
      );
    } finally {
      setLoading(false);
    }
  }
  /** Xử lý submit bằng React để không tải lại trang và làm mất state của phiên. */
  function submit(event: FormEvent) {
    event.preventDefault();
    void send(query);
  }
  return (
    <>
      <div className="page-heading">
        <div>
          <p className="eyebrow">TRỢ LÝ KIẾN THỨC</p>
          <h1>Mỗi câu hỏi, một bước hiểu thêm.</h1>
          <p>Tra cứu tài liệu NIDDK bằng RAG và đối chiếu nguồn bằng chứng.</p>
        </div>
        <button
          className="button button-outline"
          disabled={loading || messages.length === 0}
          onClick={() => {
            setMessages([]);
            setShareProfile(false);
          }}
        >
          <Plus size={16} /> Cuộc trò chuyện mới
        </button>
      </div>
      <div className="profile-context-bar">
        <label>
          <input
            type="checkbox"
            checked={shareProfile}
            disabled={loading || !features}
            onChange={(event) => setShareProfile(event.target.checked)}
          />{' '}
          Dùng hồ sơ trong phiên cho câu hỏi này
        </label>
        <span>
          {features
            ? `Đã có 21 trường · BMI ${features.BMI}. Có thể hỏi “Nếu BMI giảm 3 thì sao?”.`
            : 'Chưa có hồ sơ đủ 21 trường. Bạn vẫn hỏi kiến thức và đối chiếu BMI được.'}
        </span>
      </div>
      <div className="chat-layout">
        <section className="panel chat-panel">
          <div className="chat-panel-header">
            <span className="assistant-avatar">
              <Sparkles size={19} />
            </span>
            <div>
              <strong>GlucoGuide Assistant</strong>
              <small>Kiến thức từ tài liệu · Câu trả lời tiếng Việt</small>
            </div>
            <span className="tag">Custom RAG</span>
          </div>
          <div className="chat-messages" aria-live="polite">
            {messages.length === 0 ? (
              <div className="chat-welcome">
                <span className="welcome-icon">
                  <BookOpen size={30} strokeWidth={1.5} />
                </span>
                <h2>Bạn đang muốn tìm hiểu điều gì?</h2>
                <p>
                  Bắt đầu với một câu hỏi về kiến thức tiểu đường.
                  <br />
                  Mỗi nhận định cần có bằng chứng trong kho tài liệu.
                </p>
                <div className="suggestions">
                  {suggestions.map((question) => (
                    <button key={question} onClick={() => void send(question)}>
                      {question}
                      <ArrowUp size={14} />
                    </button>
                  ))}
                </div>
              </div>
            ) : (
              messages.map((message) => (
                <div className="message-pair" key={message.id}>
                  <div className="user-message">{message.question}</div>
                  <div className="assistant-message">
                    <span className="assistant-avatar">
                      <Sparkles size={16} />
                    </span>
                    <div>
                      {message.result ? (
                        <Answer result={message.result} />
                      ) : message.error ? (
                        <div role="alert" className="error-box">
                          {message.error}
                        </div>
                      ) : (
                        <p className="thinking">
                          <LoaderCircle size={16} className="spin" /> Đang tìm bằng chứng và xử lý
                          câu hỏi…
                        </p>
                      )}
                    </div>
                  </div>
                </div>
              ))
            )}
          </div>
          <form className="chat-composer" onSubmit={submit}>
            <label className="sr-only" htmlFor="chat-query">
              Câu hỏi của bạn
            </label>
            <textarea
              id="chat-query"
              rows={2}
              maxLength={2000}
              placeholder="Nhập câu hỏi kiến thức về tiểu đường…"
              value={query}
              disabled={loading}
              onChange={(event) => setQuery(event.target.value)}
            />
            <button
              aria-label="Gửi câu hỏi"
              className="send-button"
              disabled={loading || !query.trim()}
            >
              {loading ? <LoaderCircle className="spin" size={18} /> : <ArrowUp size={20} />}
            </button>
          </form>
          <p className="chat-disclaimer">
            Không nhập thông tin định danh. Lịch sử và hồ sơ chỉ giữ trong bộ nhớ tab; chỉ dùng form
            khi bạn bật lựa chọn phía trên.
          </p>
        </section>
        <aside className="results-column">
          <AgentTrace result={latest} />
          <section className="panel source-note">
            <MessageCircle size={20} />
            <h3>Minh bạch từ nguồn</h3>
            <p>Nguồn chỉ xuất hiện khi truy xuất được tài liệu và trích dẫn vượt qua kiểm tra.</p>
            <p>Nếu thiếu API key, bằng chứng hoặc Gemini gián đoạn, trợ lý sẽ báo giới hạn.</p>
            <a
              href="https://www.niddk.nih.gov/health-information/diabetes"
              target="_blank"
              rel="noreferrer"
            >
              Tìm hiểu thư viện NIDDK ↗
            </a>
          </section>
        </aside>
      </div>
      <details className="graph-disclosure">
        <summary>
          <BookOpen size={17} /> Mở đồ thị và kiểm chứng nguồn Neo4j
        </summary>
        <KnowledgeGraph />
      </details>
    </>
  );
}
