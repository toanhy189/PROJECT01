/** Kiểm thử UI qua trình duyệt: model thật, fallback và bố cục di động. */
import { expect, test } from '@playwright/test';

// So sánh điểm hiển thị với response API, không cố định một score minh họa trong test.
test('form 21 trường gọi mô hình thật và hiển thị trace', async ({ page }) => {
  const errors: string[] = [];
  page.on('pageerror', (error) => errors.push(error.message));
  await page.goto('/');
  await expect(page.getByText('API sẵn sàng')).toBeVisible();
  await expect(page.getByRole('heading', { name: 'Hiểu chỉ số. Hiểu sức khỏe.' })).toBeVisible();
  await page.screenshot({ path: 'test-results/dashboard-desktop.png', fullPage: true });
  await page.getByRole('button', { name: 'Bắt đầu phân loại' }).click();
  const selects = page.locator('.feature-form select');
  expect(await selects.count()).toBe(18);
  for (const select of await selects.all()) await select.selectOption({ index: 1 });
  await page.locator('#BMI').fill('25');
  await page.locator('#MentHlth').fill('0');
  await page.locator('#PhysHlth').fill('0');
  await expect(page.getByText('21/21 trường')).toBeVisible();
  const responsePromise = page.waitForResponse((response) =>
    response.url().endsWith('/api/v1/analyze'),
  );
  await page.getByRole('button', { name: 'Phân loại chỉ số', exact: true }).last().click();
  const response = await responsePromise;
  expect(response.status()).toBe(200);
  const data = await response.json();
  expect(data.prediction_result.model_version).toMatch(/^cdc-mlp-/);
  await expect(page.locator('.score-value')).toHaveText(
    data.prediction_result.model_score.toFixed(4),
  );
  await expect(page.locator('.trace-list li')).toHaveCount(3);
  await expect(page.getByText('Prediction Agent', { exact: true })).toBeVisible();
  expect(errors).toEqual([]);
  await page.screenshot({ path: 'test-results/prediction-desktop.png', fullPage: true });
});

// API test được cấu hình không có key, nên trường hợp này không gọi dịch vụ Gemini thật.
test('chat thiếu Gemini key trả fallback minh bạch không gắn nguồn giả', async ({ page }) => {
  await page.goto('/');
  await page.getByRole('button', { name: 'Trợ lý kiến thức', exact: true }).click();
  await page.getByRole('button', { name: 'Tiểu đường là gì?' }).click();
  await expect(page.getByText('Phản hồi giới hạn', { exact: true }).first()).toBeVisible();
  await expect(page.locator('.answer-text')).toContainText('GEMINI_API_KEY');
  await expect(page.locator('.sources details')).toHaveCount(0);
  await expect(page.locator('.trace-list li')).toHaveCount(4);
  await page.getByRole('button', { name: 'Cuộc trò chuyện mới' }).click();
  await expect(
    page.getByRole('heading', { name: 'Bạn đang muốn tìm hiểu điều gì?' }),
  ).toBeVisible();
});

test('menu và layout di động không tràn ngang', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto('/');
  expect(
    await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth),
  ).toBeTruthy();
  await page.getByRole('button', { name: 'Mở menu' }).click();
  await page.getByRole('button', { name: 'Phân loại chỉ số', exact: true }).click();
  await expect(page.locator('#Age')).toBeVisible();
  await expect(page.locator('.sidebar')).toHaveCSS('transform', 'matrix(1, 0, 0, 1, -240, 0)');
  expect(
    await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth),
  ).toBeTruthy();
  await page.screenshot({ path: 'test-results/prediction-mobile.png', fullPage: true });
});
