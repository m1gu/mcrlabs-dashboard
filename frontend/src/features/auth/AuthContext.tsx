import type { ReactNode } from 'react'
import { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react'
import { differenceInMinutes, parseISO } from 'date-fns'
import { loginRequest } from './api'
import type { StoredAuth } from './authStorage'
import { clearStoredAuth, getStoredAuth, setStoredAuth, subscribeAuthChanges } from './authStorage'

type AuthState = {
  user: string | null
  token: string | null
  expiresAt: string | null
}

type LoginInput = {
  username: string
  password: string
}

type AuthContextValue = {
  user: string | null
  token: string | null
  expiresAt: string | null
  isAuthenticated: boolean
  isExpiringSoon: boolean
  login: (input: LoginInput) => Promise<void>
  logout: () => void
}

const AuthContext = createContext<AuthContextValue | undefined>(undefined)

function mapStoredAuth(auth: StoredAuth | null): AuthState {
  if (!auth) {
    return { user: null, token: null, expiresAt: null }
  }
  return {
    user: auth.username,
    token: auth.token,
    expiresAt: auth.expiresAt,
  }
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<AuthState>(() => mapStoredAuth(getStoredAuth()))
  const { user, token, expiresAt } = state

  useEffect(() => {
    const unsubscribe = subscribeAuthChanges((auth) => {
      setState(mapStoredAuth(auth))
    })
    return () => unsubscribe()
  }, [])

  const login = useCallback(async ({ username, password }: LoginInput) => {
    const result = await loginRequest({ username, password })
    setStoredAuth({
      token: result.access_token,
      username: result.user.username,
      expiresAt: result.expires_at,
    })
  }, [])

  const logout = useCallback(() => {
    clearStoredAuth()
  }, [])

  const isAuthenticated = Boolean(token)
  const isExpiringSoon = useMemo(() => {
    if (!expiresAt) return false
    try {
      const expiresDate = parseISO(expiresAt)
      return differenceInMinutes(expiresDate, new Date()) <= 15
    } catch {
      return false
    }
  }, [expiresAt])

  const value = useMemo<AuthContextValue>(
    () => ({
      user,
      token,
      expiresAt,
      isAuthenticated,
      isExpiringSoon,
      login,
      logout,
    }),
    [user, token, expiresAt, isAuthenticated, isExpiringSoon, login, logout],
  )

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext)
  if (!ctx) {
    throw new Error('useAuth must be used within AuthProvider')
  }
  return ctx
}
