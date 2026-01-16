import { useMemo, useState, useEffect } from 'react'
import { NavLink, Outlet, useLocation } from 'react-router-dom'
import { parseISO } from 'date-fns'
import { apiFetchV2 } from '../lib/api'
import { formatDateTimeShort } from '../utils/format'
import './dashboard.css'
import { useAuth } from '../features/auth/AuthContext'

const NAV_ITEMS = [
  { label: 'Overview', to: '/glims/overview' },
  { label: 'Tests', to: '/glims/tests' },
  { label: 'Priority Samples', to: '/glims/priority' },
  { label: 'TAT Samples', to: '/glims/tat-samples' },
]

export function DashboardGlimsPage() {
  const { user, logout } = useAuth()
  const [syncLabel, setSyncLabel] = useState<string | null>(null)
  const location = useLocation()

  const heroCopy = useMemo(() => {
    if (location.pathname.includes('/glims/priority')) {
      return {
        eyebrow: 'Priority Samples',
        title: 'Priority Samples',
        subtitle: 'Track overdue GLIMS samples, test completion, and TAT breaches.',
      }
    }
    if (location.pathname.includes('/glims/tat-samples')) {
      return {
        eyebrow: 'TAT Samples',
        title: 'TAT Samples',
        subtitle: 'Analyze the slowest reported GLIMS samples to spot turnaround bottlenecks.',
      }
    }
    if (location.pathname.includes('/glims/tests')) {
      return {
        eyebrow: 'Tests',
        title: 'Laboratory Tests',
        subtitle: 'Monitor test lifecycle from preparation to run start.',
      }
    }
    return {
      eyebrow: 'Overview',
      title: 'GLIMS Metrics',
      subtitle: 'Monitor GLIMS data with key metrics, turnaround trends, and highlighted customers.',
    }
  }, [location.pathname])

  useEffect(() => {
    let cancelled = false
    void (async () => {
      try {
        // reuse tests sync as a proxy; adjust if a GLIMS-specific status endpoint is added
        const status = await apiFetchV2<{ last_updated_at: string | null; last_sync_at: string | null }>(
          '/glims/overview/summary',
        )
        if (cancelled) return
        const candidate = status.last_sync_at || status.last_updated_at
        if (candidate) {
          const date = parseISO(candidate)
          setSyncLabel(formatDateTimeShort(date))
        } else {
          setSyncLabel(null)
        }
      } catch {
        if (!cancelled) {
          setSyncLabel(null)
        }
      }
    })()
    return () => {
      cancelled = true
    }
  }, [])

  return (
    <div className="dashboard">
      <header className="dashboard__topbar">
        <div className="dashboard__branding">
          <span className="dashboard__badge">Q</span>
          <div className="dashboard__identity">
            <span className="dashboard__environment">MCRLabs GLIMS Metrics</span>
          </div>
        </div>
        <div className="dashboard__session">
          {user && <span className="dashboard__user">User: {user}</span>}
          <button type="button" className="dashboard__logout" onClick={logout}>
            Sign out
          </button>
        </div>

        <nav className="dashboard__tabs" aria-label="Dashboard sections">
          {NAV_ITEMS.map((item) => (
            <NavLink
              key={item.label}
              to={item.to}
              className={({ isActive }) =>
                ['dashboard__tab', isActive ? 'dashboard__tab--active' : null].filter(Boolean).join(' ')
              }
              end
            >
              {item.label}
            </NavLink>
          ))}
        </nav>
      </header>

      <main className="dashboard__content">
        <section className="dashboard__hero">
          <p className="dashboard__eyebrow">{heroCopy.eyebrow}</p>
          <h1 className="dashboard__title">{heroCopy.title}</h1>
          <p className="dashboard__subtitle">{heroCopy.subtitle}</p>
          {syncLabel && <p className="dashboard__updated">Data updated through {syncLabel}</p>}
        </section>
        <Outlet />
      </main>
    </div>
  )
}
