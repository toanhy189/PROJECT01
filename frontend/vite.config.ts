/** Cấu hình React/Tailwind và proxy API local trong môi trường phát triển. */
import { defineConfig, loadEnv } from 'vite';
import react from '@vitejs/plugin-react';
import tailwindcss from '@tailwindcss/vite';

export default defineConfig(({ mode }) => {
  const target = loadEnv(mode, '.', 'VITE_').VITE_API_TARGET || 'http://127.0.0.1:8000';
  return {
    plugins: [react(), tailwindcss()],
    server: { proxy: { '/api': target, '/health': target } },
  };
});
