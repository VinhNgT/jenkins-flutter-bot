/// <reference types="vitest" />
import { defineConfig } from 'vitest/config';
import preact from '@preact/preset-vite';

export default defineConfig({
  plugins: [preact()],
  base: '/webapp/',
  build: {
    outDir: '../src/tg_jenkins_bot/webapp',
    emptyOutDir: true,
  },
  server: {
    proxy: {
      '/api/webapp': {
        target: 'http://localhost:9090',
        changeOrigin: true,
      },
    },
  },
  resolve: {
    alias: {
      '@': '/src',
    },
  },
  test: {
    environment: 'jsdom',
    setupFiles: ['./src/__tests__/setup.ts'],
    include: ['src/__tests__/**/*.test.{ts,tsx}'],
  },
});
