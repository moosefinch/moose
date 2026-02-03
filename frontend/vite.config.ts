import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

const BACKEND_URL = process.env.GPS_BACKEND_URL || 'http://localhost:8000'
const BACKEND_WS = process.env.GPS_BACKEND_WS || BACKEND_URL.replace(/^http/, 'ws')

export default defineConfig({
  plugins: [react()],
  build: {
    outDir: 'dist',
  },
  server: {
    host: '127.0.0.1',
    port: 3000,
    proxy: {
      '/api': BACKEND_URL,
      '/conversations': BACKEND_URL,
      '/health': BACKEND_URL,
      '/ws': { target: BACKEND_WS, ws: true },
    },
  },
})
