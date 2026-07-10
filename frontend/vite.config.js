import { defineConfig } from 'vite'
import solid from 'vite-plugin-solid'

export default defineConfig({
  plugins: [solid()],
  server: {
    port: 5173,
    host: '0.0.0.0',          // necesario para Docker
    proxy: {
      // Todas las peticiones /api van al backend FastAPI
      // En dev local: http://localhost:8000
      // En Docker: el nombre de servicio 'backend'
      '/api': {
        target: process.env.VITE_API_URL || 'http://localhost:8000',
        changeOrigin: true,
      }
    }
  },
  build: {
    outDir: 'dist',
    sourcemap: false,
    // 600 kB es razonable para una SPA local empaquetada en el .exe; el aviso
    // por defecto (500 kB) es solo cosmético aquí.
    chunkSizeWarningLimit: 800,
  }
})
