import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

const proxy = Object.fromEntries(['/v1', '/health', '/admin'].map(path => [path, {
  target: 'http://127.0.0.1:8010',
  // The backend allows up to five minutes for editorial preparation.
  proxyTimeout: 330_000,
  timeout: 330_000,
}]));

export default defineConfig({ plugins: [react()], base: './', server: { proxy }, preview: { proxy } });
