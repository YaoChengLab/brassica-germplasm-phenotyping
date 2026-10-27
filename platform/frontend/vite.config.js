import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vitejs.dev/config/
export default defineConfig({
  plugins: [react({
    include: "**/*.{jsx,js}", // Allow JSX in .js files
    jsxRuntime: 'automatic'
  })],
  server: {
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
        // backend serves under /api/v1 already; do not strip the /api prefix
      },
    },
  },
  build: {
    // Enable source maps in production for better error tracing
    sourcemap: true,
    // Control chunk size warnings
    chunkSizeWarningLimit: 600,
  },
})