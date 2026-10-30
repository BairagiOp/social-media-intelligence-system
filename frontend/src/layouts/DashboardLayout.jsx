import { useEffect, useId, useState } from 'react'
import { Link, NavLink, Outlet, useLocation } from 'react-router-dom'
import { Loader, Menu, X } from '../components/icons'
import { useHealth } from '../hooks/useApi'

const NAV = [
  { section: 'Overview' },
  { to: '/', label: 'Dashboard' },
  { to: '/datasets', label: 'Datasets' },
  { to: '/datasets/discovery', label: 'Dataset discovery' },
  { to: '/explorer', label: 'Data explorer' },
  { section: 'Intelligence' },
  { to: '/sentiment', label: 'Sentiment' },
  { to: '/topics', label: 'Topics' },
  { to: '/bot-detection', label: 'Automated accounts' },
  { to: '/misinformation', label: 'Misinformation' },
  { to: '/network', label: 'Network graph' },
  { section: 'Operations' },
  { to: '/training', label: 'Model training' },
  { to: '/evidence', label: 'Evidence' },
  { to: '/reports', label: 'Reports' },
  { to: '/settings', label: 'Settings' },
]

export default function DashboardLayout() {
  const { health, reachable } = useHealth(15000)
  const location = useLocation()
  const navId = useId()
  const [navOpen, setNavOpen] = useState(false)
  const [isNarrow, setIsNarrow] = useState(
    () => typeof window !== 'undefined' && window.matchMedia('(max-width: 900px)').matches
  )

  useEffect(() => {
    const mq = window.matchMedia('(max-width: 900px)')
    const onChange = (e) => setIsNarrow(e.matches)
    mq.addEventListener('change', onChange)
    return () => mq.removeEventListener('change', onChange)
  }, [])

  // Close the mobile menu after navigating, so the page is visible immediately.
  useEffect(() => setNavOpen(false), [location.pathname])

  const bootStatus = health?.bootstrap?.status
  const bootBusy = bootStatus === 'RUNNING' || bootStatus === 'PENDING'
  const navHidden = isNarrow && !navOpen

  return (
    <div className="app-shell">
      <a className="skip-link" href="#main-content">Skip to main content</a>

      <div className="topbar">
        <button
          type="button"
          className="btn"
          aria-expanded={navOpen}
          aria-controls={navId}
          onClick={() => setNavOpen((v) => !v)}
        >
          {navOpen ? <X size={15} /> : <Menu size={15} />}
          {navOpen ? 'Close menu' : 'Menu'}
        </button>
        <span className="brand-name">HawkEYE</span>
      </div>

      <aside className="sidebar" id={navId} hidden={navHidden}>
        <div className="brand">
          <span className="brand-name">HawkEYE</span>
          <span className="brand-sub">SMDPIS</span>
        </div>

        <nav aria-label="Sections">
          {NAV.map((item, i) =>
            item.section ? (
              <h2 className="nav-section" key={`s${i}`}>{item.section}</h2>
            ) : (
              <NavLink
                key={item.to}
                to={item.to}
                end={item.to === '/'}
                className={({ isActive }) => `nav-link ${isActive ? 'active' : ''}`}
              >
                {item.label}
              </NavLink>
            )
          )}
        </nav>

        <div className="sidebar-footer">
          <div className="footer-text">
            {reachable ? (
              <>
                <span className="status-dot ok" />
                API online, version {health?.version || 'unknown'}
              </>
            ) : (
              <>
                <span className="status-dot down" />
                API offline
              </>
            )}
          </div>
          <div className="footer-text">
            {bootBusy ? (
              <span className="flex" style={{ gap: 6 }}>
                <Loader size={11} />
                Preparing sample data and models
              </span>
            ) : bootStatus === 'DEGRADED' ? (
              <>
                <span className="status-dot busy" />
                Setup finished with warnings
              </>
            ) : reachable ? (
              'Ready'
            ) : null}
          </div>
          <div className="footer-text">Public and synthetic data only</div>
          <div className="footer-links">
            <Link to="/terms">Terms of Service</Link>
            <Link to="/privacy">Privacy Policy</Link>
          </div>
        </div>
      </aside>

      <main className="main" id="main-content">
        {!reachable && (
          <div className="notice error mb-16" role="alert">
            <div>
              <strong>The backend is not responding.</strong> Start it with{' '}
              <code>uvicorn app.main:app --app-dir backend --port 8000</code>, then this
              page will reconnect on its own within 15 seconds.
            </div>
          </div>
        )}
        {reachable && bootBusy && (
          <div className="notice info mb-16" role="status">
            <div>
              First run in progress. HawkEYE is generating the synthetic sample dataset and
              training the four baseline models. Figures stay incomplete until that finishes,
              which takes about a minute.
            </div>
          </div>
        )}
        <Outlet />
      </main>
    </div>
  )
}
