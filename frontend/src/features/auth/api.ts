import { API_AUTH_BASE_URL } from '../../config'

type LoginPayload = {
  username: string
  password: string
}

export type LoginResponse = {
  access_token: string
  token_type: string
  expires_at: string
  expires_in: number
  user: {
    username: string
  }
}

export async function loginRequest(payload: LoginPayload): Promise<LoginResponse> {
  const response = await fetch(`${API_AUTH_BASE_URL}/auth/login`, {
    method: 'POST',
    headers: {
      Accept: 'application/json',
      'Content-Type': 'application/json',
    },
    body: JSON.stringify(payload),
  })

  if (!response.ok) {
    let message = response.statusText
    try {
      const data = (await response.json()) as { detail?: string | { error?: string; locked_until?: string } }
      if (data?.detail) {
        if (typeof data.detail === 'string') {
          message = data.detail
        } else if (typeof data.detail === 'object' && data.detail.error) {
          message = data.detail.error
        }
      }
    } catch {
      // ignore parse issues
    }
    throw new Error(message || 'Unable to authenticate')
  }

  return (await response.json()) as LoginResponse
}
