/** Tự chạy API/Vite và kiểm thử bằng Edge headless với Gemini key rỗng ở process test. */
import { defineConfig } from '@playwright/test';
import { fileURLToPath } from 'node:url';
import path from 'node:path';

const root = fileURLToPath(new URL('..', import.meta.url));
const python = path.join(
  root,
  '.venv',
  process.platform === 'win32' ? 'Scripts/python.exe' : 'bin/python',
);
// Cổng test riêng, không dừng hoặc tái sử dụng server người dùng đang mở.
const apiPort = process.env.PLAYWRIGHT_API_PORT || '8105';
const webPort = process.env.PLAYWRIGHT_WEB_PORT || '5185';

export default defineConfig({
  testDir: './e2e',
  workers: 1,
  timeout: 30000,
  fullyParallel: false,
  reporter: [['list'], ['json', { outputFile: '../artifacts/development_playwright.json' }]],
  use: {
    baseURL: `http://127.0.0.1:${webPort}`,
    channel: 'msedge',
    headless: true,
    screenshot: 'only-on-failure',
  },
  webServer: [
    {
      command: `"${python}" -X utf8 -m uvicorn backend.main:app --host 127.0.0.1 --port ${apiPort}`,
      cwd: root,
      env: { GEMINI_API_KEY: '' },
      url: `http://127.0.0.1:${apiPort}/health`,
      timeout: 60000,
    },
    {
      command: `npm run dev -- --strictPort --port ${webPort}`,
      url: `http://127.0.0.1:${webPort}`,
      env: { VITE_API_TARGET: `http://127.0.0.1:${apiPort}` },
      timeout: 30000,
    },
  ],
});
