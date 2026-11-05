/** Hiển thị trace nhận từ backend, không tự thêm node hoặc thời gian minh họa. */
import { Check, Clock3, GitBranch, TriangleAlert } from 'lucide-react';
import type { Analysis } from '../types/api';

/** Khi chưa có request hoàn tất, hiển thị trạng thái chờ thay cho dữ liệu giả. */
export default function AgentTrace({ result }: { result: Analysis | null }) {
  return (
    <section className="panel trace-panel">
      <div className="section-title">
        <GitBranch size={18} />
        <h3>Luồng xử lý Agent</h3>
        {result && <span className="tag">{result.agent_trace.length} node</span>}
      </div>
      {result ? (
        <>
          <ol className="trace-list">
            {result.agent_trace.map((entry, index) => (
              <li key={index}>
                <span className={`trace-dot ${entry.status}`}>
                  {entry.status === 'ok' ? <Check size={12} /> : <TriangleAlert size={12} />}
                </span>
                <div>
                  <strong>{entry.agent}</strong>
                  <small>
                    {entry.status === 'ok'
                      ? 'Hoàn tất'
                      : entry.status === 'fallback'
                        ? 'Phản hồi giới hạn'
                        : 'Dịch vụ chưa khả dụng'}
                  </small>
                </div>
                <time>{entry.latency_ms.toFixed(1)} ms</time>
              </li>
            ))}
          </ol>
          <div className="trace-footer">
            <Clock3 size={13} /> Tổng thời gian node:{' '}
            {result.agent_trace.reduce((sum, item) => sum + item.latency_ms, 0).toFixed(1)} ms
          </div>
          <small className="request-id">Mã yêu cầu: {result.request_id}</small>
        </>
      ) : (
        <div className="empty-state">
          <span className="empty-orbit">
            <GitBranch size={24} />
          </span>
          <p>Trace sẽ xuất hiện khi bạn gửi yêu cầu.</p>
          <small>Thứ tự và thời gian ghi trực tiếp từ LangGraph.</small>
        </div>
      )}
    </section>
  );
}
