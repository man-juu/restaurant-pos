/// <reference types="vitest/config" />
import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

export default defineConfig({
  plugins: [react()],
  server: {
    host: true,
    // Proxies /api/* unchanged to the API, so the browser sees one origin (as with Caddy in prod).
    proxy: {
      '/api': {
        target: process.env.API_URL ?? 'http://localhost:8000',
      },
    },
  },
  test: { environment: 'jsdom' },
})
