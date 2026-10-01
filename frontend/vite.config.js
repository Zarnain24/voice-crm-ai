import { defineConfig, loadEnv } from 'vite'
import react from '@vitejs/plugin-react'

// The dev server acts as a small backend-for-frontend: it proxies /api to FastAPI and
// injects the API key server-side, so the key is never shipped to the browser bundle.
export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, '..', '') // read the project-root .env (not exposed to client code)
  const proxy = {
    '/api': {
      target: env.CRM_API_URL || 'http://localhost:8000',
      changeOrigin: true,
      headers: { 'X-API-Key': env.CRM_API_KEY ?? '' },
    },
  }
  return {
    plugins: [react()],
    server: { port: 5173, proxy },
    preview: { port: 5173, proxy },
  }
})
