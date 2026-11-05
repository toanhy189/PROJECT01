/** Kiểm thử trace local thật và render attribution bằng fixture UI, không gọi Gemini. */
import { expect, test } from '@playwright/test';

test('API GraphRAG local trả đường đi và context khi Gemini key rỗng', async ({ request }) => {
  const info = await request.get('/api/v1/retrieval-info');
  const configuration = await info.json();
  test.skip(configuration.status !== 'ready', 'Cần build snapshot nguồn thật trước.');
  const response = await request.post('/api/v1/retrieve', {
    data: {
      user_query:
        'Tiền tiểu đường liên quan nguy cơ típ 2 và thay đổi lối sống nào có thể giúp trì hoãn?',
      retrieval_mode: 'graph',
    },
  });
  expect(response.status()).toBe(200);
  const result = await response.json();
  expect(result.trace.graph.backend).toBe(configuration.graph_backend);
  if (configuration.graph_backend === 'neo4j') {
    expect(result.trace.graph.connected).toBe(true);
    expect(result.trace.graph.query_count).toBeGreaterThan(0);
    const stats = await request.get('/api/v1/graph/stats');
    expect((await stats.json()).status).toBe('ready');
  }
  expect(result.trace.channel_counts.graph).toBeGreaterThan(0);
  expect(
    result.trace.graph.paths.some((path: { used_in_context: boolean }) => path.used_in_context),
  ).toBeTruthy();
  expect(result.trace.context_chunk_ids.length).toBeGreaterThan(0);
  expect(
    result.documents.every((source: { metadata: { source_url: string } }) =>
      source.metadata.source_url.startsWith('https://www.niddk.nih.gov/'),
    ),
  ).toBeTruthy();
});

test('fixture UI hiển thị revision, giấy phép wiki và đường tìm evidence', async ({ page }) => {
  await page.route('**/api/v1/chat', async (route) => {
    await route.fulfill({
      json: {
        request_id: 'ui-fixture',
        intent: 'knowledge',
        prediction_result: null,
        generated_answer: 'Nội dung chỉ dành cho kiểm thử giao diện. [S1]',
        safety_status: 'passed',
        errors: [],
        agent_trace: [],
        citations: [
          {
            citation_id: 'S1',
            document_id: 'wiki-fixture',
            chunk_id: 'fixture',
            title: 'Nguồn kiểm thử UI',
            section: 'Definition',
            quote: 'Software-only fixture.',
            source_url: 'https://en.wikipedia.org/w/index.php?oldid=42',
            source_provider: 'wikipedia',
            revision_id: 42,
            license: 'Test license',
            license_url: 'https://creativecommons.org/licenses/by-sa/4.0/',
            attribution_url: 'https://en.wikipedia.org/wiki/Software',
          },
        ],
        retrieval_trace: {
          graph: {
            backend: 'neo4j',
            connected: true,
            latency_ms: 3.2,
            linked_entities: [
              { entity_id: 'alpha', matched_alias: 'Alpha', method: 'controlled_alias' },
            ],
            paths: [
              {
                entities: ['alpha', 'beta'],
                relations: [{ subject: 'alpha', predicate: 'CANNOT_DIAGNOSE', object: 'beta' }],
                chunk_ids: ['fixture'],
                hops: 1,
                used_in_context: true,
              },
            ],
          },
        },
      },
    });
  });
  await page.goto('/');
  await page.getByRole('button', { name: 'Trợ lý kiến thức', exact: true }).click();
  await page.getByRole('button', { name: 'Tiểu đường là gì?' }).click();
  await page.locator('.sources details').first().locator('summary').click();
  await expect(page.getByRole('link', { name: 'Đọc tài liệu gốc' })).toHaveAttribute(
    'href',
    'https://en.wikipedia.org/w/index.php?oldid=42',
  );
  await expect(page.getByRole('link', { name: 'Test license' })).toBeVisible();
  await page.getByText('Cách đồ thị tìm bằng chứng', { exact: true }).click();
  await expect(page.getByText('Nguồn truy xuất: Neo4j · đã kết nối · 3.2 ms')).toBeVisible();
  await expect(page.getByText('alpha → beta', { exact: true })).toBeVisible();
  await expect(
    page.getByText('alpha — không thể dùng để chẩn đoán → beta', { exact: true }),
  ).toBeVisible();
});
