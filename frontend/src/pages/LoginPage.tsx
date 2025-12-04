import { LoginForm } from '../features/auth/LoginForm'
import '../styles/login.css'

export function LoginPage() {
  return (
    <div className="login-page">
      <div className="login-page__panel">
        <div className="login-page__brand">
          <span className="login-page__badge">Q</span>
          <div>
            <p className="login-page__eyebrow">Dashboard Access</p>
            <h1>Sign in</h1>
            <p className="login-page__copy">Use the credentials provided by the operations team.</p>
          </div>
        </div>
        <LoginForm />
      </div>
    </div>
  )
}
