import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import { resolve } from 'node:path';

export default defineConfig({
  plugins: [react()],
  test: { environment: 'jsdom', globals: true },
  build: {
    rollupOptions: { input: {
      director: resolve(process.cwd(), 'index.html'),
      postproduction: resolve(process.cwd(), 'postproduction.html'),
    }},
  },
  server: { host: '127.0.0.1', port: 3000, proxy: { '/api': 'http://127.0.0.1:8000' } },
});
