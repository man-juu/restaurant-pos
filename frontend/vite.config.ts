/// <reference types="vitest/config" />
import tailwindcss from '@tailwindcss/vite'
import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'
import { VitePWA } from 'vite-plugin-pwa'

export default defineConfig({
  plugins: [
    react(),
    tailwindcss(),
    // Installable app (PWA): "Install" on desktop, "Add to home screen" on phones.
    VitePWA({
      registerType: 'autoUpdate',
      includeAssets: ['icon.svg', 'backgrounds/*.svg', 'push-sw.js'],
      manifest: {
        name: 'Restaurant POS',
        short_name: 'POS',
        description: 'Point of sale and back office for restaurants and kitchens',
        theme_color: '#0f151c',
        background_color: '#0f151c',
        display: 'standalone',
        start_url: '/',
        icons: [
          { src: 'icon.svg', sizes: 'any', type: 'image/svg+xml', purpose: 'any' },
          { src: 'icon.svg', sizes: 'any', type: 'image/svg+xml', purpose: 'maskable' },
        ],
      },
      workbox: {
        // Online-first (docs/01): cache the app shell only, never API responses.
        navigateFallbackDenylist: [/^\/api\//, /^\/admin-api\//],
        runtimeCaching: [],
        importScripts: ['push-sw.js'], // FR-NTF-005 web push handlers
      },
    }),
  ],
  server: {
    host: true,
    // Same-origin proxies, as Caddy does in production: cookies stay first-party.
    proxy: {
      '/api': { target: process.env.API_URL ?? 'http://localhost:8000' },
      '/admin-api': { target: process.env.ADMIN_API_URL ?? 'http://localhost:8001' },
    },
  },
  test: { environment: 'jsdom', include: ['src/**/*.test.{ts,tsx}'] },
})
