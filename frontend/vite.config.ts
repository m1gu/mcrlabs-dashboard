import { defineConfig, loadEnv } from 'vite'
import react from '@vitejs/plugin-react-swc'

const DEFAULT_API_BASE_URL = 'https://615c98lc-8000.use.devtunnels.ms'
//const DEFAULT_API_BASE_URL = 'http://localhost:8000'

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '')
  const apiBaseUrl = env.API_BASE_URL || env.VITE_API_BASE_URL || DEFAULT_API_BASE_URL

  return {
    plugins: [react()],
    server: {
      port: 5177,
    },
    preview: {
      port: 5177,
    },
    define: {
      'import.meta.env.API_BASE_URL': JSON.stringify(apiBaseUrl),
      'import.meta.env.VITE_API_BASE_URL': JSON.stringify(apiBaseUrl),
    },
  }
})
