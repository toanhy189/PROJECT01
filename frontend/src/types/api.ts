/** Kiểu dữ liệu trao đổi với FastAPI; tên trường giữ nguyên theo schema backend. */
export type Features = Record<string, number>;
/** Score chưa hiệu chuẩn, không phải xác suất chẩn đoán. */
export interface Prediction {
  model_score: number;
  predicted_class: 0 | 1;
  threshold: number;
  model_version: string;
  limitations: string;
}
/** Nguồn đã được backend đối chiếu với bằng chứng của request hiện tại. */
export interface Citation {
  citation_id: string;
  document_id: string;
  chunk_id: string;
  title: string;
  section: string;
  source_url: string;
  quote: string;
  source_provider?: string | null;
  revision_id?: number | null;
  license?: string | null;
  license_url?: string | null;
  attribution_url?: string | null;
  section_scope?: string | null;
  changes?: string | null;
}
/** Đường truy xuất đồ thị chỉ dùng tìm bằng chứng, không phải suy luận chẩn đoán. */
export interface GraphPath {
  entities: string[];
  relations: {
    relation_id?: string;
    subject: string;
    predicate: string;
    object: string;
    polarity?: 'positive' | 'negative' | 'uncertain';
    qualifiers?: string;
  }[];
  chunk_ids: string[];
  hops: number;
  used_in_context?: boolean;
  evidence?: {
    evidence_id: string;
    relation_id: string;
    document_id: string;
    chunk_id: string;
    quote: string;
    source_url: string;
    content_version: string;
  }[];
}
/** Trace retrieval không chứa khóa API hoặc thông tin sức khỏe người dùng. */
export interface RetrievalTrace {
  mode?: string;
  snapshot_id?: string;
  corpus_version?: string;
  warnings?: string[];
  channel_counts?: Record<string, number>;
  graph?: {
    backend?: 'neo4j' | 'networkx';
    status?: string;
    connected?: boolean | null;
    latency_ms?: number;
    linked_entities: { entity_id: string; matched_alias: string; method: string }[];
    paths: GraphPath[];
  };
}
/** Một node thực sự đã chạy, kèm thời gian đo ở backend. */
export interface Trace {
  agent: string;
  status: 'ok' | 'error' | 'fallback';
  latency_ms: number;
}
/** Kết quả workflow cho cả ba intent, bao gồm lỗi và phản hồi giới hạn. */
export interface Analysis {
  request_id: string;
  intent: 'prediction' | 'knowledge' | 'combined';
  prediction_result: Prediction | null;
  generated_answer: string;
  citations: Citation[];
  safety_status: 'passed' | 'fallback';
  agent_trace: Trace[];
  errors: string[];
  retrieval_trace?: RetrievalTrace;
  profile_hash?: string | null;
  measurement_result?: {
    rule_id: string;
    value: number;
    origin: string;
    category: string;
    scope: string;
  } | null;
  scenario_result?: Scenario | null;
}

export interface Scenario {
  before: Prediction;
  after: Prediction;
  score_delta: number;
  changes: Record<string, { before: number; after: number }>;
  original_hash: string;
  modified_hash: string;
  modified_features: Features;
  interpretation: string;
}

export interface Comparison {
  profile_hash: string;
  models: (Prediction & { model_name: string })[];
  errors: { model_name: string; code: string; message: string }[];
  agreement: boolean;
}

export interface Inspection {
  model_version: string;
  baseline_roc_auc: number;
  test_rows: number;
  repeats: number;
  results: { feature: string; mean_roc_auc_drop: number; shuffle_std: number; rank: number }[];
}

export interface Retrieval {
  documents: { text: string; metadata: Record<string, string | number | boolean> }[];
  trace: RetrievalTrace;
}

export interface DatasetStatistics {
  count: number;
  class_0: number;
  class_1: number;
  class_1_fraction: number | null;
  total_clean_rows: number;
  source: string;
  source_url: string;
  dataset_sha256: string;
  limitations: string;
}
/** Metadata model; ready=false khi artifact chưa có hoặc không tương thích. */
export interface ModelInfo {
  ready: boolean;
  model_version: string | null;
  threshold: number | null;
  feature_names: string[];
  limitations: string;
}
