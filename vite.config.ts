import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    host: true,
    // В dev фронт на :5173 проксирует запросы к бэку на :8000 — чтобы фронт мог
    // звать относительный /talk (тот же путь, что в собранном виде за туннелем).
    // 127.0.0.1, а НЕ localhost: на Node 17+ порядок резолва DNS «как отдали»,
    // и localhost уходит в ::1 первым, а uvicorn с --host 127.0.0.1 слушает
    // только IPv4 → прокси падает с ECONNREFUSED ::1:8000.
    // Префикс '/talk' покрывает и '/talk_stream'.
    proxy: {
      '/talk': 'http://127.0.0.1:8000',
      '/monologue': 'http://127.0.0.1:8000',
      '/health': 'http://127.0.0.1:8000',
      // Картинки заданий тоже идут через бэкенд — Unsplash из РФ не открывается.
      '/img': 'http://127.0.0.1:8000',
    },
  },
})
