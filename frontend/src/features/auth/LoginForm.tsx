import { FormEvent, useState } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'
import { useAuth } from './AuthContext'
import './login-form.css'

type LocationState = {
  from?: {
    pathname?: string
  }
}

export function LoginForm() {
  const navigate = useNavigate()
  const location = useLocation()
  const from = (location.state as LocationState | null)?.from?.pathname || '/dashboard'

  const { login, isExpiringSoon } = useAuth()
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [isSubmitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setError(null)
    setSubmitting(true)
    try {
      await login({ username, password })
      navigate(from, { replace: true })
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Unable to sign in'
      setError(message)
      setSubmitting(false)
    }
  }

  return (
    <form className="login-form" onSubmit={handleSubmit} aria-label="Sign in form">
      <div className="login-form__group">
        <label htmlFor="username">Username</label>
        <input
          id="username"
          name="username"
          type="text"
          autoComplete="username"
          value={username}
          onChange={(event) => setUsername(event.target.value)}
          required
        />
      </div>

      <div className="login-form__group">
        <label htmlFor="password">Password</label>
        <input
          id="password"
          name="password"
          type="password"
          autoComplete="current-password"
          value={password}
          onChange={(event) => setPassword(event.target.value)}
          required
        />
      </div>

      {error && (
        <p role="alert" className="login-form__error">
          {error}
        </p>
      )}

      <button type="submit" disabled={isSubmitting}>
        {isSubmitting ? 'Validating...' : 'Sign in'}
      </button>

      {isExpiringSoon && (
        <p className="login-form__warning">Your previous session was about to expire. A new token will be issued.</p>
      )}
    </form>
  )
}
