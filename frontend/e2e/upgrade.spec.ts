/** Các luồng mới chạy backend/model thật; screenshot là dữ liệu kiểm thử phần mềm. */
import { expect, test, type Page } from '@playwright/test';

async function fillProfile(page: Page) {
  await page.getByRole('button', { name: 'Phân loại chỉ số', exact: true }).first().click();
  for (const select of await page.locator('.feature-form select').all())
    await select.selectOption({ index: 1 });
  await page.locator('#Age').selectOption('2');
  await page.locator('#BMI').fill('25');
  await page.locator('#MentHlth').fill('0');
  await page.locator('#PhysHlth').fill('0');
  await page.getByRole('button', { name: 'Phân loại chỉ số', exact: true }).last().click();
  await expect(page.locator('.score-value')).toBeVisible();
}

test('bản thử và so sánh hai model chạy thật, không sửa form gốc', async ({ page }) => {
  await page.goto('/');
  await fillProfile(page);
  await page.locator('#trial-value').fill('35');
  const pending = page.waitForResponse((response) => response.url().endsWith('/api/v1/scenarios'));
  await page.getByRole('button', { name: 'So sánh trước–sau' }).click();
  const response = await pending;
  expect(response.status()).toBe(200);
  const scenario = await response.json();
  await expect(page.locator('.score-pair strong').first()).toHaveText(
    scenario.before.model_score.toFixed(4),
  );
  await expect(page.locator('.score-pair strong').last()).toHaveText(
    scenario.after.model_score.toFixed(4),
  );
  await expect(page.locator('#BMI')).toHaveValue('25');
  await page.getByRole('button', { name: 'So sánh hai mô hình' }).click();
  await expect(page.locator('.comparison-results article')).toHaveCount(2);
  await expect(page.locator('.comparison-results')).toContainText('Logistic Regression');
  await page.getByRole('button', { name: 'Ảnh hưởng 21 đặc trưng' }).click();
  await expect(page.locator('.importance-report li')).toHaveCount(21);
  await page.screenshot({ path: 'test-results/upgrade-model-lab.png', fullPage: true });
  await page.locator('.model-lab').screenshot({ path: 'test-results/upgrade-model-lab-panel.png' });
  await page.getByRole('button', { name: 'Áp dụng bản thử vào form' }).click();
  await expect(page.locator('#BMI')).toHaveValue('35');
  await expect(page.locator('.stale-notice')).toContainText('Đầu vào đã thay đổi');
});

test('BMI có nguồn và câu hỏi nối tiếp giữ đúng hồ sơ, không cần key', async ({ page }) => {
  await page.goto('/');
  await fillProfile(page);
  await page.getByRole('button', { name: 'Trợ lý kiến thức', exact: true }).click();
  await page.getByLabel('Dùng hồ sơ trong phiên cho câu hỏi này').check();
  await page.locator('#chat-query').fill('BMI của mình có quá cao không?');
  await page.getByRole('button', { name: 'Gửi câu hỏi' }).click();
  await expect(page.locator('.answer-text').last()).toContainText('BMI 25');
  await expect(page.locator('.answer-text').last()).toContainText('thừa cân');
  await page.locator('#chat-query').fill('Nếu giảm 3 thì sao?');
  await page.getByRole('button', { name: 'Gửi câu hỏi' }).click();
  await expect(page.locator('.answer-text').last()).toContainText('thử BMI từ 25 thành 22');
  await page.getByRole('button', { name: 'Phân loại chỉ số', exact: true }).first().click();
  await expect(page.locator('#BMI')).toHaveValue('25');
  await page.getByRole('button', { name: 'Trợ lý kiến thức', exact: true }).click();
  await expect(page.locator('.message-pair')).toHaveCount(2);
  await page.screenshot({ path: 'test-results/upgrade-chat-profile.png', fullPage: true });
  await page.getByRole('button', { name: 'Cuộc trò chuyện mới' }).click();
  await expect(page.getByLabel('Dùng hồ sơ trong phiên cho câu hỏi này')).not.toBeChecked();
});

test('tiếng Việt nguyên vẹn, font hệ thống và các trang không tràn trên di động', async ({
  page,
}) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto('/');
  expect(await page.evaluate(() => document.documentElement.lang)).toBe('vi');
  expect(await page.evaluate(() => getComputedStyle(document.body).fontFamily)).toContain(
    'Segoe UI',
  );
  await expect(page.getByRole('heading', { name: 'Hiểu chỉ số. Hiểu sức khỏe.' })).toBeVisible();
  for (const name of ['Phân loại chỉ số', 'Trợ lý kiến thức']) {
    await page.getByRole('button', { name: 'Mở menu' }).click();
    await page.getByRole('button', { name, exact: true }).first().click();
    await expect(page.locator('.sidebar')).toHaveCSS('transform', 'matrix(1, 0, 0, 1, -240, 0)');
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(
      true,
    );
    expect(await page.locator('body').innerText()).not.toMatch(/\uFFFD|Ã¡|áº|á»/);
  }
  await page.screenshot({ path: 'test-results/upgrade-chat-mobile.png', fullPage: true });
});

test('thống kê khảo sát trả số đếm từ CSV thật', async ({ page }) => {
  await page.goto('/');
  await page.locator('.dataset-explorer summary').click();
  await page.getByRole('button', { name: 'Đếm hồ sơ' }).click();
  await expect(page.locator('.dataset-result')).toContainText('hồ sơ phù hợp');
  await expect(page.locator('.dataset-result')).toContainText('không phải xác suất');
});

test('đồ thị trong giao diện truy vấn Neo4j và mở đúng nguồn của cạnh', async ({
  page,
  request,
}) => {
  const info = await request.get('/api/v1/graph/stats');
  test.skip((await info.json()).status !== 'ready', 'Cần snapshot Neo4j thật đã sẵn sàng.');
  await page.goto('/');
  await page.getByRole('button', { name: 'Trợ lý kiến thức', exact: true }).click();
  await page.locator('.graph-disclosure > summary').click();
  await page.getByRole('button', { name: 'Truy xuất', exact: true }).click();
  await expect(page.locator('.graph-canvas')).toBeVisible();
  await expect(page.locator('.graph-evidence article').first()).toBeVisible();
  await expect(page.locator('.graph-evidence')).toContainText('RelationFact');
  await expect(page.locator('.graph-evidence a').first()).toHaveAttribute(
    'href',
    /^https:\/\/www\.niddk\.nih\.gov\//,
  );
  await page.locator('.graph-panel').screenshot({ path: 'test-results/upgrade-neo4j-panel.png' });
});

test('phản hồi bản thử cũ không ghi đè form đã thay đổi', async ({ page }) => {
  await page.goto('/');
  await fillProfile(page);
  let release: () => void = () => {};
  const gate = new Promise<void>((resolve) => {
    release = resolve;
  });
  let arrived: () => void = () => {};
  const arrival = new Promise<void>((resolve) => {
    arrived = resolve;
  });
  await page.route('**/api/v1/scenarios', async (route) => {
    const response = await route.fetch();
    arrived();
    await gate;
    await route.fulfill({ response });
  });
  await page.locator('#trial-value').fill('35');
  await page.getByRole('button', { name: 'So sánh trước–sau' }).click();
  await arrival;
  await page.locator('#BMI').fill('30');
  const completed = page.waitForResponse((response) =>
    response.url().endsWith('/api/v1/scenarios'),
  );
  release();
  await completed;
  await expect(page.locator('#BMI')).toHaveValue('30');
  await expect(page.locator('.stale-notice')).toBeVisible();
  await expect(page.locator('.scenario-result')).toHaveCount(0);
});
