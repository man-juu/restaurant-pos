/// <reference types="vitest/config" />
import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

export default defineConfig({
  plugins: [react()],
  server: {
    host: true,
    // The dev server proxies API calls so the browser sees one origin (same as Caddy in production).
    proxy: {
      '/api': {
        target: process.env.API_URL ?? 'http://localhost:8000',
        rewrite: (p) => p.replace(/^\/api/, ''),
      },
    },
  },
  test: { environment: 'jsdom' },
})
