/** Form CDC đúng mã, giữ hồ sơ trong phiên và gắn kết quả với đầu vào thực tế. */
import { useRef, useState, type FormEvent } from 'react';
import {
  Activity,
  ArrowRight,
  LoaderCircle,
  RotateCcw,
  ShieldCheck,
  TriangleAlert,
} from 'lucide-react';
import AgentTrace from '../components/AgentTrace';
import Answer from '../components/Answer';
import ModelLab from '../components/ModelLab';
import { groups, oneBased } from '../data/features';
import { api } from '../services/api';
import { useProfile } from '../state/ProfileContext';
import type { Features } from '../types/api';

export default function Prediction() {
  const {
    values,
    setValues,
    features,
    snapshotKey,
    analysis: result,
    setAnalysis: setResult,
    analysisKey,
    setAnalysisKey,
    clear,
    analysisSequence,
  } = useProfile();
  const [question, setQuestion] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const requestVersion = analysisSequence;
  const latestKey = useRef(snapshotKey);
  latestKey.current = snapshotKey;
  const filled = Object.values(values).filter((value) => value !== '').length;
  const stale = !!result && analysisKey !== snapshotKey;

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!features) {
      setError('Hãy kiểm tra đủ 21 thông tin và miền giá trị.');
      return;
    }
    const current = ++requestVersion.current;
    const submittedKey = snapshotKey;
    setLoading(true);
    setError('');
    try {
      const response = await api.analyze(features, question);
      if (current === requestVersion.current && submittedKey === latestKey.current) {
        setResult(response);
        setAnalysisKey(submittedKey);
      }
    } catch (cause) {
      if (current === requestVersion.current)
        setError(cause instanceof Error ? cause.message : 'Có lỗi xử lý yêu cầu.');
    } finally {
      if (current === requestVersion.current) setLoading(false);
    }
  }
  function applyTrial(modified: Features) {
    setValues(
      Object.fromEntries(Object.entries(modified).map(([key, value]) => [key, String(value)])),
    );
  }
  return (
    <>
      <div className="page-heading">
        <div>
          <p className="eyebrow">PHÂN LOẠI CHỈ SỐ</p>
          <h1>Tìm hiểu từ dữ liệu của bạn</h1>
          <p>Hoàn thành 21 trường, đọc kết quả và khám phá cách mô hình phản ứng với thay đổi.</p>
        </div>
        <span className="academic-badge">
          <ShieldCheck size={15} /> Hồ sơ chỉ giữ trong tab
        </span>
      </div>
      <div className="prediction-layout">
        <form onSubmit={submit} className="feature-form">
          <div className="form-progress">
            <div>
              <strong>Thông tin đầu vào</strong>
              <span>{filled}/21 trường</span>
            </div>
            <progress max={21} value={filled} />
          </div>
          <fieldset disabled={loading} className="form-fieldset">
            {groups.map((group, index) => (
              <section className="panel form-group" key={group.title}>
                <div className="form-group-heading">
                  <span>{String(index + 1).padStart(2, '0')}</span>
                  <div>
                    <h2>{group.title}</h2>
                    <p>{group.subtitle}</p>
                  </div>
                </div>
                <div className="fields-grid">
                  {group.fields.map((field) => (
                    <div className="field" key={field.key}>
                      <label htmlFor={field.key}>
                        {field.label} <span>*</span>
                      </label>
                      {field.options ? (
                        <select
                          id={field.key}
                          required
                          value={values[field.key] ?? ''}
                          onChange={(event) =>
                            setValues({ ...values, [field.key]: event.target.value })
                          }
                        >
                          <option value="" disabled>
                            Chọn thông tin
                          </option>
                          {field.options.map((label, i) => (
                            <option key={label} value={i + (oneBased.has(field.key) ? 1 : 0)}>
                              {label}
                            </option>
                          ))}
                        </select>
                      ) : (
                        <input
                          id={field.key}
                          type="number"
                          required
                          min={field.min}
                          max={field.max}
                          step={field.key === 'BMI' ? '0.1' : '1'}
                          placeholder={`${field.min}–${field.max}`}
                          value={values[field.key] ?? ''}
                          onChange={(event) =>
                            setValues({ ...values, [field.key]: event.target.value })
                          }
                        />
                      )}
                      {field.help && <small>{field.help}</small>}
                    </div>
                  ))}
                </div>
              </section>
            ))}
            <section className="panel form-group">
              <label className="optional-label" htmlFor="consultation">
                Câu hỏi kiến thức kèm theo <span>Không bắt buộc</span>
              </label>
              <textarea
                id="consultation"
                maxLength={2000}
                rows={3}
                placeholder="Ví dụ: BMI của mình có quá cao không?"
                value={question}
                onChange={(event) => setQuestion(event.target.value)}
              />
              <small className="helper">
                Câu hỏi có thể được đối chiếu bằng quy tắc có nguồn hoặc truy xuất tài liệu.
              </small>
            </section>
          </fieldset>
          {error && (
            <div role="alert" className="error-box">
              {error}
            </div>
          )}
          <div className="form-actions">
            <button
              type="button"
              className="button button-ghost"
              disabled={loading}
              onClick={() => {
                requestVersion.current += 1;
                clear();
                setQuestion('');
                setError('');
              }}
            >
              <RotateCcw size={15} /> Nhập lại
            </button>
            <button className="button button-primary" disabled={loading}>
              {loading ? (
                <>
                  <LoaderCircle className="spin" size={17} /> Đang xử lý…
                </>
              ) : (
                <>
                  Phân loại chỉ số <ArrowRight size={17} />
                </>
              )}
            </button>
          </div>
          {features && result?.prediction_result && !stale && (
            <ModelLab features={features} onApply={applyTrial} />
          )}
        </form>
        <aside className="results-column">
          <section className={`panel result-panel ${stale ? 'result-stale' : ''}`}>
            <div className="section-title">
              <Activity size={18} />
              <h3>Kết quả mô hình</h3>
            </div>
            {stale && (
              <div className="stale-notice" role="status">
                <TriangleAlert size={17} />
                <p>
                  Đầu vào đã thay đổi. Kết quả dưới đây thuộc hồ sơ trước; hãy bấm Phân loại chỉ số
                  để cập nhật.
                </p>
              </div>
            )}
            {result?.prediction_result ? (
              <>
                <p className="score-label">ĐIỂM MÔ HÌNH · THANG 0–1</p>
                <div className="score-value">{result.prediction_result.model_score.toFixed(4)}</div>
                <div
                  className="threshold-track"
                  role="img"
                  aria-label={`Điểm ${result.prediction_result.model_score.toFixed(4)}, ngưỡng ${result.prediction_result.threshold.toFixed(4)}`}
                >
                  <span style={{ width: `${result.prediction_result.model_score * 100}%` }} />
                  <i style={{ left: `${result.prediction_result.threshold * 100}%` }} />
                </div>
                <p className="class-label">
                  Lớp {result.prediction_result.predicted_class} ·{' '}
                  {result.prediction_result.predicted_class === 1
                    ? 'Tiền tiểu đường hoặc tiểu đường'
                    : 'Không tiểu đường'}{' '}
                  theo nhãn khảo sát
                </p>
                <dl className="model-details">
                  <div>
                    <dt>Ngưỡng phân loại</dt>
                    <dd>{result.prediction_result.threshold.toFixed(4)}</dd>
                  </div>
                  <div>
                    <dt>Phiên bản</dt>
                    <dd>{result.prediction_result.model_version}</dd>
                  </div>
                </dl>
                <details className="score-explainer">
                  <summary>Đọc điểm và ngưỡng như thế nào?</summary>
                  <p>
                    Máy tính điểm từ 21 thông tin. Điểm thấp hơn ngưỡng được xếp lớp 0; từ ngưỡng
                    trở lên được xếp lớp 1. Điểm {result.prediction_result.model_score.toFixed(4)}{' '}
                    không phải xác suất mắc bệnh hoặc độ chính xác của mô hình.
                  </p>
                </details>
                <Answer result={result} />
                {!stale && (
                  <button
                    type="button"
                    className="button button-outline lab-shortcut"
                    onClick={() =>
                      document
                        .getElementById('model-lab')
                        ?.scrollIntoView({ behavior: 'smooth', block: 'start' })
                    }
                  >
                    Thử thay đổi và giải thích điểm <ArrowRight size={15} />
                  </button>
                )}
              </>
            ) : result ? (
              <Answer result={result} />
            ) : (
              <div className="empty-state">
                <span className="empty-orbit">
                  <Activity size={28} />
                </span>
                <h4>Sẵn sàng khi bạn sẵn sàng</h4>
                <p>Nhập thông tin bên trái để xem kết quả từ mô hình đã huấn luyện.</p>
              </div>
            )}
          </section>
          <AgentTrace result={result} />
          <div className="privacy-note">
            <ShieldCheck size={17} />
            <p>
              Hồ sơ được giữ trong bộ nhớ tab để thử thay đổi và hỏi tiếp khi bạn chọn dùng. Không
              lưu bệnh án lâu dài.
            </p>
          </div>
        </aside>
      </div>
    </>
  );
}
