/** Công cụ khám phá model thật: bản thử độc lập, ngưỡng riêng và báo cáo có nguồn. */
import { useEffect, useRef, useState } from 'react';
import { FlaskConical, ArrowRight, BarChart3, GitCompareArrows, LoaderCircle } from 'lucide-react';
import { api } from '../services/api';
import { groups } from '../data/features';
import type { Comparison, Features, Inspection, Scenario } from '../types/api';

const labels = Object.fromEntries(
  groups.flatMap((group) => group.fields.map((field) => [field.key, field.label])),
);

export default function ModelLab({
  features,
  onApply,
}: {
  features: Features;
  onApply: (features: Features) => void;
}) {
  const [field, setField] = useState('BMI');
  const [value, setValue] = useState(String(features.BMI));
  const [scenario, setScenario] = useState<Scenario | null>(null);
  const [comparison, setComparison] = useState<Comparison | null>(null);
  const [inspection, setInspection] = useState<Inspection | null>(null);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState('');
  const revision = useRef(0);
  const key = JSON.stringify(features);
  useEffect(() => {
    revision.current += 1;
    setScenario(null);
    setComparison(null);
    setValue(String(features[field]));
    setError('');
    setBusy('');
    return () => {
      revision.current += 1;
    };
  }, [key, field]);
  async function run(action: string, override?: number, targetField = field) {
    const current = ++revision.current;
    setBusy(action);
    setError('');
    try {
      if (action === 'scenario') {
        const result = await api.scenario(features, { [targetField]: override ?? Number(value) });
        if (current === revision.current) setScenario(result);
      } else if (action === 'compare') {
        const result = await api.compare(features);
        if (current === revision.current) setComparison(result);
      } else {
        const result = await api.inspection();
        if (current === revision.current) setInspection(result);
      }
    } catch (cause) {
      if (current === revision.current)
        setError(cause instanceof Error ? cause.message : 'Chưa chạy được công cụ.');
    } finally {
      if (current === revision.current) setBusy('');
    }
  }
  const definition = groups.flatMap((group) => group.fields).find((item) => item.key === field)!;
  const minimum = ['Age', 'Education', 'Income', 'GenHlth'].includes(field) ? 1 : 0;
  return (
    <section className="panel model-lab" id="model-lab">
      <div className="section-title">
        <FlaskConical size={19} />
        <h3>Khám phá mô hình</h3>
        <span className="tag">Chạy cục bộ</span>
      </div>
      <p className="section-description">
        Thử một thay đổi, giữ nguyên các thông tin còn lại. Hồ sơ gốc được giữ riêng.
      </p>
      <div className="lab-controls">
        <div className="field">
          <label htmlFor="trial-field">Thông tin cần thử</label>
          <select
            id="trial-field"
            value={field}
            disabled={!!busy}
            onChange={(event) => setField(event.target.value)}
          >
            {groups
              .flatMap((group) => group.fields)
              .map((item) => (
                <option key={item.key} value={item.key}>
                  {item.label}
                </option>
              ))}
          </select>
        </div>
        <div className="field">
          <label htmlFor="trial-value">Giá trị bản thử</label>
          {definition.options ? (
            <select
              id="trial-value"
              value={value}
              disabled={!!busy}
              onChange={(event) => {
                setValue(event.target.value);
                setScenario(null);
              }}
            >
              {definition.options.map((label, index) => (
                <option key={label} value={index + minimum}>
                  {label}
                </option>
              ))}
            </select>
          ) : (
            <input
              id="trial-value"
              type="number"
              value={value}
              min={definition.min}
              max={definition.max}
              step={field === 'BMI' ? '0.1' : '1'}
              disabled={!!busy}
              onChange={(event) => {
                setValue(event.target.value);
                setScenario(null);
              }}
            />
          )}
        </div>
      </div>
      <div className="tool-actions">
        <button
          className="button button-primary"
          type="button"
          disabled={!!busy || value.trim() === ''}
          onClick={() => void run('scenario')}
        >
          So sánh trước–sau <ArrowRight size={15} />
        </button>
        <button
          className="button button-outline"
          type="button"
          disabled={!!busy}
          onClick={() => void run('scenario', features.BMI - 3, 'BMI')}
        >
          Thử BMI giảm 3
        </button>
      </div>
      {scenario && (
        <div className="scenario-result" aria-live="polite">
          <div className="score-pair">
            <div>
              <small>Hồ sơ gốc</small>
              <strong>{scenario.before.model_score.toFixed(4)}</strong>
              <span>Lớp {scenario.before.predicted_class}</span>
            </div>
            <ArrowRight size={20} />
            <div>
              <small>Bản thử</small>
              <strong>{scenario.after.model_score.toFixed(4)}</strong>
              <span>Lớp {scenario.after.predicted_class}</span>
            </div>
          </div>
          <p>
            Chênh lệch điểm:{' '}
            <strong>
              {scenario.score_delta >= 0 ? '+' : ''}
              {scenario.score_delta.toFixed(4)}
            </strong>{' '}
            · Ngưỡng {scenario.before.threshold.toFixed(4)}
          </p>
          {Object.entries(scenario.changes).map(([name, change]) => (
            <p key={name}>
              {labels[name]}: {change.before} → {change.after}
            </p>
          ))}
          <p className="helper">{scenario.interpretation}</p>
          <button
            type="button"
            className="button button-outline"
            onClick={() => onApply(scenario.modified_features)}
          >
            Áp dụng bản thử vào form
          </button>
        </div>
      )}
      <div className="tool-actions secondary-tools">
        <button
          type="button"
          className="button button-outline"
          disabled={!!busy}
          onClick={() => void run('compare')}
        >
          <GitCompareArrows size={16} /> So sánh hai mô hình
        </button>
        <button
          type="button"
          className="button button-outline"
          disabled={!!busy}
          onClick={() => void run('inspection')}
        >
          <BarChart3 size={16} /> Ảnh hưởng 21 đặc trưng
        </button>
      </div>
      {busy && (
        <p className="inline-status" role="status">
          <LoaderCircle className="spin" size={16} /> Đang chạy công cụ{' '}
          {busy === 'scenario' ? 'trước–sau' : busy === 'compare' ? 'so sánh' : 'phân tích'}…
        </p>
      )}
      {error && (
        <p role="alert" className="error-box">
          {error}
        </p>
      )}
      {comparison && (
        <div className="comparison-results">
          <div className="comparison-grid">
            {comparison.models.map((model) => (
              <article key={model.model_name}>
                <small>{model.model_name}</small>
                <strong>{model.model_score.toFixed(4)}</strong>
                <p>
                  Ngưỡng {model.threshold.toFixed(4)} · Lớp {model.predicted_class}
                </p>
              </article>
            ))}
          </div>
          <p className="helper">
            {comparison.models.length < 2
              ? 'Một mô hình chưa sẵn sàng.'
              : comparison.agreement
                ? 'Hai mô hình cùng lớp trên hồ sơ này.'
                : 'Hai mô hình khác lớp trên hồ sơ này.'}{' '}
            Điểm không phải xác suất bệnh; mỗi mô hình dùng ngưỡng riêng.
          </p>
          {comparison.errors.map((item) => (
            <p className="error-box" key={item.code}>
              {item.model_name}: {item.message}
            </p>
          ))}
        </div>
      )}
      {inspection && (
        <div className="importance-report">
          <h4>Mức phụ thuộc chung của mô hình</h4>
          <p className="helper">
            Đo trên {inspection.test_rows.toLocaleString('vi-VN')} hồ sơ kiểm tra,{' '}
            {inspection.repeats} lần xáo trộn. Không phải giải thích đóng góp riêng của hồ sơ này.
          </p>
          <ol>
            {inspection.results.map((item) => (
              <li key={item.feature}>
                <span>{labels[item.feature] || item.feature}</span>
                <meter
                  min={0}
                  max={Math.max(...inspection.results.map((entry) => entry.mean_roc_auc_drop))}
                  value={Math.max(0, item.mean_roc_auc_drop)}
                />
                <small>
                  {Math.abs(item.mean_roc_auc_drop) < 0.00005
                    ? '≈0'
                    : item.mean_roc_auc_drop.toFixed(4)}
                </small>
              </li>
            ))}
          </ol>
          <p className="helper">
            Số hiển thị là mức giảm khả năng phân biệt hai nhóm (ROC-AUC), không phải phần trăm nguy
            hiểm. Phiên bản: {inspection.model_version}.
          </p>
        </div>
      )}
    </section>
  );
}
