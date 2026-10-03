import { defineConfig } from 'vite';

export default defineConfig({
  build: { target: 'esnext', assetsInlineLimit: 0, chunkSizeWarningLimit: 4000 },
  server: { host: '127.0.0.1', port: 5200 },
});
