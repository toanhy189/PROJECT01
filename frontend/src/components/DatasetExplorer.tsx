/** Thống kê từ nhãn khảo sát thật, không chuyển tỷ lệ nhóm thành nguy cơ cá nhân. */
import { useState, type FormEvent } from 'react';
import { Database, LoaderCircle } from 'lucide-react';
import { api } from '../services/api';
import { groups } from '../data/features';
import type { DatasetStatistics } from '../types/api';

export default function DatasetExplorer() {
  const [minimum, setMinimum] = useState('25');
  const [maximum, setMaximum] = useState('35');
  const [age, setAge] = useState('');
  const [result, setResult] = useState<DatasetStatistics | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  async function submit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError('');
    setResult(null);
    try {
      setResult(
        await api.dataset({
          bmi_min: Number(minimum),
          bmi_max: Number(maximum),
          ...(age ? { age_group: Number(age) } : {}),
        }),
      );
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Chưa đọc được dữ liệu.');
    } finally {
      setBusy(false);
    }
  }
  return (
    <details className="panel dataset-explorer">
      <summary>
        <Database size={18} /> Khám phá dữ liệu khảo sát CDC{' '}
        <span className="tag">Thống kê có nguồn</span>
      </summary>
      <p className="section-description">
        Đếm nhãn trong dữ liệu đã loại trùng. Đây là khảo sát BRFSS 2015, không phải dự đoán cho
        người đang nhập form.
      </p>
      <form onSubmit={submit}>
        <fieldset disabled={busy}>
          <div className="lab-controls">
            <div className="field">
              <label htmlFor="dataset-min">BMI từ</label>
              <input
                id="dataset-min"
                type="number"
                min={12}
                max={98}
                step="0.1"
                required
                value={minimum}
                onChange={(event) => setMinimum(event.target.value)}
              />
            </div>
            <div className="field">
              <label htmlFor="dataset-max">BMI đến</label>
              <input
                id="dataset-max"
                type="number"
                min={12}
                max={98}
                step="0.1"
                required
                value={maximum}
                onChange={(event) => setMaximum(event.target.value)}
              />
            </div>
            <div className="field">
              <label htmlFor="dataset-age">Nhóm tuổi</label>
              <select id="dataset-age" value={age} onChange={(event) => setAge(event.target.value)}>
                <option value="">Tất cả nhóm tuổi</option>
                {groups[0].fields[0].options!.map((label, index) => (
                  <option key={label} value={index + 1}>
                    {label}
                  </option>
                ))}
              </select>
            </div>
          </div>
          <button type="submit" className="button button-outline">
            {busy ? <LoaderCircle size={16} className="spin" /> : <Database size={16} />} Đếm hồ sơ
          </button>
        </fieldset>
      </form>
      {error && (
        <p role="alert" className="error-box">
          {error}
        </p>
      )}
      {result && (
        <div className="dataset-result" aria-live="polite">
          <strong>{result.count.toLocaleString('vi-VN')} hồ sơ phù hợp</strong>
          <div className="comparison-grid">
            <article>
              <small>Nhãn khảo sát 0</small>
              <strong>{result.class_0.toLocaleString('vi-VN')}</strong>
              <p>Không tiểu đường theo nhãn</p>
            </article>
            <article>
              <small>Nhãn khảo sát 1</small>
              <strong>{result.class_1.toLocaleString('vi-VN')}</strong>
              <p>Tiền tiểu đường hoặc tiểu đường</p>
            </article>
          </div>
          <p className="helper">{result.limitations}</p>
          <a href={result.source_url} target="_blank" rel="noreferrer">
            Nguồn UCI · {result.source}
          </a>
          <p className="helper">Dấu dữ liệu: {result.dataset_sha256.slice(0, 16)}…</p>
        </div>
      )}
    </details>
  );
}
