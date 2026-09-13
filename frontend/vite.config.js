import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// The bundle is committed to frontend/dist so the demo runs from FastAPI alone,
// with no `npm install` required on demo day.
export default defineConfig({
  plugins: [react()],
  build: {
    outDir: 'dist',
    emptyOutDir: true,
    sourcemap: false,
  },
  server: {
    port: 5173,
    // During `npm run dev` the API runs separately on :8000.
    proxy: {
      '/cases': 'http://127.0.0.1:8000',
      '/health': 'http://127.0.0.1:8000',
      '/rules': 'http://127.0.0.1:8000',
      '/classifications': 'http://127.0.0.1:8000',
    },
  },
})
