import tailwindcss from '@tailwindcss/vite'
import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    // The API runs on :8010 in dev; in production FastAPI serves this build itself.
    proxy: { '/api': 'http://localhost:8010' },
  },
})
