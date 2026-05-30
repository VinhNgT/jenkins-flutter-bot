/// <reference types="vitest" />
import { defineConfig } from 'vitest/config';
import preact from '@preact/preset-vite';

export default defineConfig({
  plugins: [preact()],
  base: '/webapp-admin/',
  build: {
    outDir: '../src/config_hub/webapp',
    emptyOutDir: true,
  },
  server: {
    proxy: {
      '/api/webapp-admin': {
        target: 'http://localhost:8880',
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
    include: ['src/__tests__/**/*.test.{ts,tsx}'],
  },
});
