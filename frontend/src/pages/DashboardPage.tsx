import { useEffect, useMemo, useState } from 'react'
import { NavLink, Outlet, useLocation } from 'react-router-dom'
import { parseISO } from 'date-fns'
import { apiFetch } from '../lib/api'
import { formatDateTimeShort } from '../utils/format'
import './dashboard.css'
import { useAuth } from '../features/auth/AuthContext'

type NavItem = {
  label: string
  to?: string
  disabled?: boolean
}

const NAV_ITEMS: NavItem[] = [
  { label: 'Overview', to: '/dashboard' },
  { label: 'Priority Orders', to: '/dashboard/priority-orders' },
  { label: 'TAT Orders', to: '/dashboard/tat-orders' },
]

export function DashboardPage() {
  const location = useLocation()
  const { user, logout } = useAuth()
  const [syncLabel, setSyncLabel] = useState<string | null>(null)

  const heroCopy = useMemo(() => {
    if (location.pathname.includes('priority-orders')) {
      return {
        eyebrow: 'Priority Orders',
        title: 'Priority Orders',
        subtitle: 'Monitor overdue orders, warning signals, and ready-to-report samples to stay ahead of SLAs.',
      }
    }
    if (location.pathname.includes('tat-orders')) {
      return {
        eyebrow: 'TAT Orders',
        title: 'TAT Orders',
        subtitle: 'Analyze the slowest reported orders to understand turnaround bottlenecks.',
      }
    }
    return {
      eyebrow: 'Overview',
      title: 'MCRLabs Metrics',
      subtitle: 'Monitor QBench activity with key metrics, turnaround trends, and highlighted customers.',
    }
  }, [location.pathname])

  useEffect(() => {
    let cancelled = false
    void (async () => {
      try {
        const status = await apiFetch<{ entity: string; updated_at: string | null }>('/metrics/sync/status', {
          entity: 'tests',
        })
        if (cancelled) return
        if (status.updated_at) {
          const date = parseISO(status.updated_at)
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
            <span className="dashboard__environment">MCRLabs Metrics</span>
          </div>
        </div>
        <div className="dashboard__session">
          {user && <span className="dashboard__user">User: {user}</span>}
          <button type="button" className="dashboard__logout" onClick={logout}>
            Sign out
          </button>
        </div>

        <nav className="dashboard__tabs" aria-label="Dashboard sections">
          {NAV_ITEMS.map((item) =>
            item.to ? (
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
            ) : (
              <span key={item.label} className="dashboard__tab dashboard__tab--disabled">
                {item.label}
              </span>
            ),
          )}
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
