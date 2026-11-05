/** Gọi API qua Vite proxy, chuẩn hóa lỗi hiển thị và giới hạn thời gian chờ. */
import type {
  Analysis,
  Features,
  ModelInfo,
  Scenario,
  Comparison,
  Inspection,
  Retrieval,
  DatasetStatistics,
} from '../types/api';

/** Gửi GET/POST; hủy yêu cầu quá hạn và luôn dọn timer dù thành công hay lỗi. */
async function request<T>(path: string, body?: unknown): Promise<T> {
  const controller = new AbortController();
  // Chờ đủ hai lời gọi embedding/LLM, mỗi lời gọi có timeout riêng ở backend.
  const timer = window.setTimeout(() => controller.abort(), 70000);
  try {
    const response = await fetch(path, {
      method: body === undefined ? 'GET' : 'POST',
      headers: body === undefined ? undefined : { 'Content-Type': 'application/json' },
      body: body === undefined ? undefined : JSON.stringify(body),
      signal: controller.signal,
    });
    const data = await response.json().catch(() => null);
    if (!response.ok)
      throw new Error(
        (data?.detail || 'Không thể kết nối dịch vụ.') +
          (data?.fields?.length ? ` (${data.fields.join(', ')})` : ''),
      );
    if (data === null) throw new Error('Phản hồi máy chủ không hợp lệ.');
    return data as T;
  } catch (error) {
    if (error instanceof DOMException && error.name === 'AbortError')
      throw new Error('Yêu cầu quá thời gian chờ. Vui lòng thử lại.');
    if (error instanceof TypeError)
      throw new Error('Không kết nối được API. Kiểm tra backend đang chạy.');
    throw error;
  } finally {
    window.clearTimeout(timer);
  }
}

// Khóa Gemini chỉ ở backend; frontend chỉ gửi payload đúng endpoint được công bố.
export const api = {
  health: () => request<{ status: string }>('/health'),
  modelInfo: () => request<ModelInfo>('/api/v1/model-info'),
  analyze: (patient_features: Features, user_query: string) =>
    request<Analysis>('/api/v1/analyze', { patient_features, user_query }),
  chat: (user_query: string, patient_features?: Features, focus?: 'BMI') =>
    request<Analysis>('/api/v1/chat', {
      user_query,
      ...(patient_features ? { patient_features } : {}),
      ...(focus ? { focus } : {}),
    }),
  scenario: (patient_features: Features, changes: Record<string, number>) =>
    request<Scenario>('/api/v1/scenarios', { patient_features, changes }),
  compare: (patient_features: Features) =>
    request<Comparison>('/api/v1/models/compare', { patient_features }),
  inspection: () => request<Inspection>('/api/v1/model-inspection'),
  retrieve: (user_query: string) =>
    request<Retrieval>('/api/v1/retrieve', { user_query, retrieval_mode: 'graph' }),
  dataset: (filters: { bmi_min: number; bmi_max: number; age_group?: number }) =>
    request<DatasetStatistics>('/api/v1/dataset/query', filters),
};
