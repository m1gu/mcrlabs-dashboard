import { getEnv } from './env'

//const DEFAULT_API_BASE_URL = 'http://localhost:8000'
const DEFAULT_API_BASE_URL = 'https://615c98lc-8000.use.devtunnels.ms'

function normalizeBaseUrl(url: string): string {
  const trimmed = url.replace(/\/+$/, '')
  if (trimmed.endsWith('/api/v1')) {
    return trimmed.slice(0, -'/api/v1'.length)
  }
  if (trimmed.endsWith('/api')) {
    return trimmed.slice(0, -'/api'.length)
  }
  return trimmed
}

const RAW_API_ROOT = getEnv('API_BASE_URL', getEnv('VITE_API_BASE_URL', DEFAULT_API_BASE_URL))

export const API_ROOT_URL = normalizeBaseUrl(RAW_API_ROOT)
export const API_V1_BASE_URL = `${API_ROOT_URL}/api/v1`
export const API_AUTH_BASE_URL = `${API_ROOT_URL}/api`

export const DEFAULT_DATE_RANGE_DAYS = 7
