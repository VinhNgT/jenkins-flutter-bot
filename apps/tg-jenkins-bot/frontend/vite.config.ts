import { defineConfig } from 'vite';
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
});
