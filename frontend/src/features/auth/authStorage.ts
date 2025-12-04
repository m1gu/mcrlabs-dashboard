import { differenceInMilliseconds, parseISO } from 'date-fns'

const STORAGE_KEY = 'dq-auth'

export type StoredAuth = {
  token: string
  username: string
  expiresAt: string
}

type Listener = (auth: StoredAuth | null) => void

let cachedAuth: StoredAuth | null = null
const listeners = new Set<Listener>()

function isExpired(auth: StoredAuth): boolean {
  try {
    const expires = parseISO(auth.expiresAt)
    return differenceInMilliseconds(expires, new Date()) <= 0
  } catch {
    return true
  }
}

function loadFromStorage(): StoredAuth | null {
  if (typeof window === 'undefined') {
    return null
  }

  const raw = window.localStorage.getItem(STORAGE_KEY)
  if (!raw) return null

  try {
    const parsed = JSON.parse(raw) as StoredAuth
    return parsed
  } catch {
    return null
  }
}

function persist(auth: StoredAuth | null): void {
  if (typeof window === 'undefined') {
    cachedAuth = auth
    return
  }
  if (auth) {
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(auth))
  } else {
    window.localStorage.removeItem(STORAGE_KEY)
  }
  cachedAuth = auth
  listeners.forEach((listener) => listener(cachedAuth))
}

export function getStoredAuth(): StoredAuth | null {
  if (!cachedAuth) {
    cachedAuth = loadFromStorage()
  }
  if (cachedAuth && isExpired(cachedAuth)) {
    persist(null)
    return null
  }
  return cachedAuth
}

export function setStoredAuth(auth: StoredAuth): void {
  persist(auth)
}

export function clearStoredAuth(): void {
  persist(null)
}

export function getAuthToken(): string | null {
  return getStoredAuth()?.token ?? null
}

export function subscribeAuthChanges(listener: Listener): () => void {
  listeners.add(listener)
  return () => {
    listeners.delete(listener)
  }
}
