import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

const BACKEND_PORT = process.env.HYPERAGENT_PORT || '8000'

// https://vite.dev/config/
export default defineConfig({
  plugins: [vue()],
  server: {
    port: 5174,
    proxy: {
      '/api': {
        target: `http://127.0.0.1:${BACKEND_PORT}`,
        changeOrigin: true,
      },
    },
  },
  build: {
    outDir: 'dist',
    assetsDir: 'assets',
  },
})
