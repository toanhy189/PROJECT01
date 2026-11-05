/** Vẽ các quan hệ thực từ trace Neo4j, mở đúng evidence theo relation_id. */
import { useState, type FormEvent } from 'react';
import { GitBranch, Search, ExternalLink, LoaderCircle } from 'lucide-react';
import { api } from '../services/api';
import type { Retrieval } from '../types/api';

const names: Record<string, string> = {
  diabetes: 'Tiểu đường',
  type_1_diabetes: 'Tiểu đường típ 1',
  type_2_diabetes: 'Tiểu đường típ 2',
  gestational_diabetes: 'Tiểu đường thai kỳ',
  prediabetes: 'Tiền tiểu đường',
  insulin_resistance: 'Kháng insulin',
  insulin: 'Insulin',
  pancreas: 'Tuyến tụy',
  blood_glucose: 'Đường huyết',
  bmi: 'Chỉ số BMI',
  obesity: 'Thừa cân / béo phì',
  severe_obesity: 'Béo phì nặng',
  family_history: 'Tiền sử gia đình',
  physical_inactivity: 'Ít vận động',
  physical_activity: 'Vận động',
  weight_loss: 'Giảm cân',
  healthy_eating: 'Ăn uống lành mạnh',
  age_risk: 'Yếu tố tuổi',
  waist: 'Vòng eo',
  a1c_test: 'Xét nghiệm HbA1c',
  fpg_test: 'Đường huyết lúc đói',
  rpg_test: 'Đường huyết ngẫu nhiên',
  ogtt: 'Dung nạp glucose',
  glucose_meter: 'Máy đo đường huyết',
  thirst: 'Khát nhiều',
  frequent_urination: 'Tiểu nhiều',
  fatigue: 'Mệt mỏi',
  heart_disease: 'Bệnh tim',
};
const predicates: Record<string, string> = {
  HAS_SUBTYPE: 'có nhóm',
  HAS_ASSOCIATED_SYMPTOM: 'có triệu chứng được đề cập',
  RISK_FACTOR_FOR: 'là yếu tố nguy cơ của',
  ASSOCIATED_WITH: 'có liên quan đến',
  USED_TO_ASSESS: 'dùng để đánh giá',
  MEASURES: 'đo lường',
  MAY_REDUCE_RISK_OF: 'có thể giúp giảm nguy cơ',
  CANNOT_DIAGNOSE: 'không thể dùng để chẩn đoán',
  PRODUCES: 'sản xuất',
};
const label = (id: string) => names[id] || id.replaceAll('_', ' ');

export default function KnowledgeGraph() {
  const [query, setQuery] = useState('BMI liên quan đến tiểu đường típ 2 như thế nào?');
  const [data, setData] = useState<Retrieval | null>(null);
  const [selected, setSelected] = useState(0);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  async function search(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError('');
    setData(null);
    setSelected(0);
    try {
      setData(await api.retrieve(query));
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Chưa đọc được đồ thị.');
    } finally {
      setBusy(false);
    }
  }
  const paths = data?.trace.graph?.paths ?? [];
  const relations = [
    ...new Map(
      paths
        .flatMap((path) => path.relations)
        .map((relation) => [
          relation.relation_id || `${relation.subject}-${relation.predicate}-${relation.object}`,
          relation,
        ]),
    ).values(),
  ].slice(0, 12);
  const ids = [...new Set(relations.flatMap((relation) => [relation.subject, relation.object]))];
  const coordinates = (id: string) => {
    const index = ids.indexOf(id);
    return { x: 115 + (index % 3) * 220, y: 60 + Math.floor(index / 3) * 110 };
  };
  const relation = relations[selected];
  const evidence = relation
    ? [
        ...new Map(
          paths
            .flatMap((path) => path.evidence || [])
            .filter((item) => item.relation_id === relation.relation_id)
            .map((item) => [item.evidence_id, item]),
        ).values(),
      ]
    : [];
  return (
    <section className="panel graph-panel">
      <div className="section-title">
        <GitBranch size={19} />
        <h3>Khám phá bằng chứng Neo4j</h3>
        <span className="tag">Đọc dữ liệu thật</span>
      </div>
      <p className="section-description">
        Tìm khái niệm, chọn một quan hệ và mở đoạn tài liệu hỗ trợ. Các đường nối không tự chứng
        minh quan hệ nhân quả.
      </p>
      <form className="graph-search" onSubmit={search}>
        <label className="sr-only" htmlFor="graph-query">
          Câu hỏi truy xuất đồ thị
        </label>
        <input
          id="graph-query"
          maxLength={2000}
          value={query}
          onChange={(event) => setQuery(event.target.value)}
        />
        <button type="submit" className="button button-primary" disabled={busy || !query.trim()}>
          {busy ? <LoaderCircle className="spin" size={16} /> : <Search size={16} />} Truy xuất
        </button>
      </form>
      {error && (
        <p role="alert" className="error-box">
          {error}
        </p>
      )}
      {data && (
        <>
          <p className="helper">
            Backend: {data.trace.graph?.backend || 'chưa có'} · {relations.length} quan hệ đang hiển
            thị · Snapshot {data.trace.snapshot_id?.slice(0, 12) || 'không có'}
          </p>
          {data.trace.graph?.status === 'fallback' && (
            <p className="error-box">
              Neo4j chưa khả dụng. Không hiển thị đồ thị minh họa thay cho dữ liệu thật.
            </p>
          )}
          {!relations.length && (
            <p className="empty-message">
              Chưa tìm được quan hệ có bằng chứng phù hợp. Thử “kháng insulin”, “HbA1c” hoặc “tiền
              tiểu đường”.
            </p>
          )}
          {!!relations.length && (
            <>
              <div className="graph-canvas">
                <svg
                  viewBox={`0 0 680 ${Math.max(150, Math.ceil(ids.length / 3) * 110 + 10)}`}
                  role="img"
                  aria-label="Đồ thị các khái niệm tìm được từ Neo4j"
                >
                  <defs>
                    <marker
                      id="graph-arrow"
                      viewBox="0 0 10 10"
                      refX="9"
                      refY="5"
                      markerWidth="6"
                      markerHeight="6"
                      orient="auto-start-reverse"
                    >
                      <path d="M0 0L10 5L0 10z" fill="#6b9e8d" />
                    </marker>
                  </defs>
                  {relations.map((edge, index) => {
                    const start = coordinates(edge.subject),
                      end = coordinates(edge.object);
                    return (
                      <line
                        key={index}
                        x1={start.x}
                        y1={start.y}
                        x2={end.x + (start.x < end.x ? -82 : 82)}
                        y2={end.y}
                        stroke={index === selected ? '#11694f' : '#c3d9cc'}
                        strokeWidth={index === selected ? 3 : 1.5}
                        markerEnd="url(#graph-arrow)"
                      />
                    );
                  })}
                  {ids.map((id) => {
                    const { x, y } = coordinates(id);
                    return (
                      <g key={id} transform={`translate(${x},${y})`}>
                        <rect
                          x={-86}
                          y={-24}
                          width={172}
                          height={48}
                          rx={12}
                          fill={
                            relation && [relation.subject, relation.object].includes(id)
                              ? '#e0f1e6'
                              : '#f7faf8'
                          }
                          stroke="#a7c7b6"
                        />
                        <text
                          textAnchor="middle"
                          dominantBaseline="middle"
                          fontSize={13}
                          fill="#205345"
                        >
                          {label(id).length > 24 ? label(id).slice(0, 23) + '…' : label(id)}
                          <title>{label(id)}</title>
                        </text>
                      </g>
                    );
                  })}
                </svg>
              </div>
              <div className="relation-buttons" aria-label="Chọn quan hệ để xem nguồn">
                {relations.map((edge, index) => (
                  <button
                    type="button"
                    key={edge.relation_id || index}
                    aria-pressed={selected === index}
                    onClick={() => setSelected(index)}
                  >
                    {label(edge.subject)}{' '}
                    <span>{predicates[edge.predicate] || edge.predicate}</span> {label(edge.object)}
                  </button>
                ))}
              </div>
              {relation && (
                <div className="graph-evidence">
                  <h4>Nguồn của quan hệ đang chọn</h4>
                  <p>
                    {label(relation.subject)} —{' '}
                    {predicates[relation.predicate] || relation.predicate} →{' '}
                    {label(relation.object)}
                  </p>
                  {relation.polarity && relation.polarity !== 'positive' && (
                    <p className="helper">
                      Trạng thái:{' '}
                      {relation.polarity === 'negative'
                        ? 'phủ định trong nguồn'
                        : 'chưa được khẳng định'}
                      .
                    </p>
                  )}
                  {relation.qualifiers && (
                    <p className="helper">Điều kiện trong nguồn: {relation.qualifiers}</p>
                  )}
                  {evidence.map((item) => (
                    <article key={item.evidence_id}>
                      <div className="provenance-chain">
                        <span>RelationFact</span> → <span>Evidence</span> → <span>Chunk</span> →{' '}
                        <span>Document</span>
                      </div>
                      <blockquote>{item.quote}</blockquote>
                      <p className="helper">
                        Quan hệ {item.relation_id.slice(0, 10)} · Bằng chứng{' '}
                        {item.evidence_id.slice(0, 10)} · Chunk {item.chunk_id} · {item.document_id}
                      </p>
                      <a href={item.source_url} target="_blank" rel="noreferrer">
                        Đọc nguồn gốc <ExternalLink size={12} />
                      </a>
                    </article>
                  ))}
                  {!evidence.length && (
                    <p className="helper">
                      Trace chưa có chi tiết evidence cho quan hệ này; không tự gắn đoạn nguồn khác.
                    </p>
                  )}
                </div>
              )}
            </>
          )}
        </>
      )}
    </section>
  );
}
