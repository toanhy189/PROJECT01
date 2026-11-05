/** Hiển thị câu trả lời dạng văn bản và nguồn backend đã kiểm tra. */
import { ExternalLink, BookOpen, ShieldCheck, TriangleAlert } from 'lucide-react';
import type { Analysis } from '../types/api';

/** Giữ ý nghĩa và hướng của quan hệ khi hiển thị đường tìm tài liệu. */
const relationLabels: Record<string, string> = {
  HAS_SUBTYPE: 'có phân nhóm',
  HAS_ASSOCIATED_SYMPTOM: 'có triệu chứng được đề cập',
  RISK_FACTOR_FOR: 'là yếu tố nguy cơ của',
  ASSOCIATED_WITH: 'có liên quan đến',
  USED_TO_ASSESS: 'được dùng để đánh giá',
  MEASURES: 'đo lường',
  MAY_REDUCE_RISK_OF: 'có thể giúp giảm nguy cơ',
  CANNOT_DIAGNOSE: 'không thể dùng để chẩn đoán',
  PRODUCES: 'tạo ra',
};

/** Dùng liên kết nguồn và quote từ response, không suy ra URL từ nội dung LLM. */
export default function Answer({ result }: { result: Analysis }) {
  return (
    <div className="answer">
      <div className={`answer-status ${result.safety_status}`}>
        {result.safety_status === 'passed' ? (
          <ShieldCheck size={15} />
        ) : (
          <TriangleAlert size={15} />
        )}
        {result.safety_status === 'passed'
          ? result.measurement_result
            ? 'Đã đối chiếu quy tắc BMI có nguồn'
            : 'Đã qua kiểm tra quy tắc an toàn'
          : 'Phản hồi giới hạn'}
      </div>
      <p className="answer-text">{result.generated_answer}</p>
      {result.citations.length > 0 && (
        <div className="sources">
          <h4>
            <BookOpen size={15} /> Nguồn bằng chứng
          </h4>
          {result.citations.map((source) => (
            <details key={source.citation_id}>
              <summary>
                <span>[{source.citation_id}]</span> {source.title}
              </summary>
              <p>{source.section}</p>
              <blockquote>{source.quote}</blockquote>
              <a href={source.source_url} target="_blank" rel="noreferrer">
                Đọc tài liệu gốc <ExternalLink size={12} />
              </a>
              {source.source_provider === 'wikipedia' && (
                <p>
                  Wikipedia · nguồn kiến thức nền · phiên bản {source.revision_id}. Chỉ lấy phần mở
                  đầu; nội dung được làm sạch và đổi định dạng.
                  {source.license_url && (
                    <>
                      {' '}
                      <a href={source.license_url} target="_blank" rel="noreferrer">
                        {source.license}
                      </a>
                      .
                    </>
                  )}
                  {source.attribution_url && (
                    <>
                      {' '}
                      <a href={source.attribution_url} target="_blank" rel="noreferrer">
                        Ghi nguồn và lịch sử bài viết
                      </a>
                      .
                    </>
                  )}
                </p>
              )}
            </details>
          ))}
        </div>
      )}
      {((result.retrieval_trace?.graph?.paths.length ?? 0) > 0 ||
        result.retrieval_trace?.graph?.status === 'fallback') && (
        <div className="sources">
          <details>
            <summary>Cách đồ thị tìm bằng chứng</summary>
            {result.retrieval_trace?.graph?.backend && (
              <p>
                Nguồn truy xuất:{' '}
                {result.retrieval_trace.graph.backend === 'neo4j' ? 'Neo4j' : 'NetworkX'}
                {result.retrieval_trace.graph.connected === true && ' · đã kết nối'}
                {result.retrieval_trace.graph.latency_ms !== undefined &&
                  ` · ${result.retrieval_trace.graph.latency_ms.toFixed(1)} ms`}
              </p>
            )}
            {result.retrieval_trace?.graph?.status === 'fallback' && (
              <p>Đồ thị tạm không khả dụng; đang dùng các nguồn truy xuất còn lại.</p>
            )}
            <p>
              Thuật ngữ nhận diện:{' '}
              {result.retrieval_trace?.graph?.linked_entities
                .map((entity) => entity.matched_alias)
                .join(', ')}
              .
            </p>
            <p>
              Đường nối giúp tìm tài liệu; không tự chứng minh quan hệ nhân quả giữa các đầu mút.
            </p>
            {result.retrieval_trace?.graph?.paths
              .filter((path) => path.used_in_context)
              .slice(0, 5)
              .map((path, index) => (
                <div key={`${path.chunk_ids.join('-')}-${index}`}>
                  <p>{path.hops} bước nối · đã đưa bằng chứng vào ngữ cảnh</p>
                  <p>{path.entities.join(' → ')}</p>
                  {path.relations.map((relation, relationIndex) => (
                    <p key={relationIndex}>
                      {relation.subject} —{' '}
                      {relationLabels[relation.predicate] ?? relation.predicate} → {relation.object}
                      {relation.polarity === 'negative' &&
                        ' (phát biểu bị phủ định trong tài liệu)'}
                      {relation.polarity === 'uncertain' && ' (chưa được khẳng định)'}
                      {relation.qualifiers && <small> · Điều kiện: {relation.qualifiers}</small>}
                    </p>
                  ))}
                  <small>Chunk nguồn: {path.chunk_ids.join(', ')}</small>
                </div>
              ))}
          </details>
        </div>
      )}
    </div>
  );
}
