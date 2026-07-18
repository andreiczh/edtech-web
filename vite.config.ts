import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    host: true,
    // В dev фронт на :5173 проксирует запросы к бэку на :8000 — чтобы фронт мог
    // звать относительный /talk (тот же путь, что в собранном виде за туннелем).
    proxy: {
      '/talk': 'http://localhost:8000',
      '/health': 'http://localhost:8000',
    },
  },
})
