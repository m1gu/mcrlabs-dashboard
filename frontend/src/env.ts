export function getEnv(key: string, fallback?: string): string {
  const value = import.meta.env[key] as string | undefined
  if (value && value.trim().length > 0) {
    return value.trim()
  }
  if (fallback !== undefined) {
    return fallback
  }
  throw new Error(`Missing required environment variable: ${key}`)
}
