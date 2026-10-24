import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// In development the API runs separately (uvicorn on :8000); in production FastAPI
// serves this build, so /api is same-origin either way.
export default defineConfig({
  plugins: [react()],
  server: { proxy: { '/api': 'http://127.0.0.1:8000' } },
})
