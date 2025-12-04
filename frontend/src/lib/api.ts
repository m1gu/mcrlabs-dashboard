import { API_V1_BASE_URL } from '../config'
import { clearStoredAuth, getAuthToken } from '../features/auth/authStorage'

type QueryValue = string | number | boolean | undefined | null

type QueryParams = Record<string, QueryValue>

function buildUrl(path: string, params?: QueryParams): string {
  const base = API_V1_BASE_URL.endsWith('/') ? API_V1_BASE_URL.slice(0, -1) : API_V1_BASE_URL
  const normalizedPath = path.startsWith('/') ? path : `/${path}`
  let url = `${base}${normalizedPath}`

  if (params) {
    const searchParams = new URLSearchParams()
    for (const [key, value] of Object.entries(params)) {
      if (value === null || value === undefined || value === '') continue
      searchParams.append(key, String(value))
    }
    const queryString = searchParams.toString()
    if (queryString) {
      url += `?${queryString}`
    }
  }

  return url
}

export async function apiFetch<T>(path: string, params?: QueryParams, init?: RequestInit): Promise<T> {
  const url = buildUrl(path, params)
  const headers = new Headers(init?.headers ?? {})
  if (!headers.has('Accept')) {
    headers.set('Accept', 'application/json')
  }
  const token = getAuthToken()
  if (token && !headers.has('Authorization')) {
    headers.set('Authorization', `Bearer ${token}`)
  }

  const response = await fetch(url, {
    ...init,
    headers,
  })

  if (!response.ok) {
    if (response.status === 401 || response.status === 423) {
      clearStoredAuth()
    }
    let detail: string = response.statusText
    try {
      const parsed = (await response.json()) as { detail?: string | { error?: string } }
      if (parsed?.detail) {
        if (typeof parsed.detail === 'string') {
          detail = parsed.detail
        } else if (typeof parsed.detail === 'object' && parsed.detail.error) {
          detail = parsed.detail.error
        }
      }
    } catch {
      // ignore JSON parsing errors, keep status text
    }
    throw new Error(`API request failed (${response.status}): ${detail}`)
  }

  return (await response.json()) as T
}
