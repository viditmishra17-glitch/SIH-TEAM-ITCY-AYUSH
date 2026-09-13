import { useCallback, useEffect, useState } from 'react'
import { getHealth } from './api.js'
import IntakePage from './pages/IntakePage.jsx'
import CasePage from './pages/CasePage.jsx'
import HistoryPage from './pages/HistoryPage.jsx'

/**
 * Hash routing on purpose: it needs no server rewrite rules, so the exact same
 * bundle works when served by FastAPI and when deployed as a static site on
 * Vercel. One less thing to configure, one less thing to break on demo day.
 */
function currentRoute() {
  const hash = window.location.hash.replace(/^#/, '') || '/'
  const parts = hash.split('/').filter(Boolean)
  if (parts[0] === 'case' && parts[1]) return { name: 'case', caseId: decodeURIComponent(parts[1]) }
  if (parts[0] === 'history') return { name: 'history' }
  return { name: 'intake' }
}

export default function App() {
  const [route, setRoute] = useState(currentRoute)
  const [health, setHealth] = useState(null)

  useEffect(() => {
    const onHashChange = () => setRoute(currentRoute())
    window.addEventListener('hashchange', onHashChange)
    return () => window.removeEventListener('hashchange', onHashChange)
  }, [])

  useEffect(() => {
    getHealth()
      .then(setHealth)
      .catch(() => setHealth({ status: 'unreachable' }))
  }, [])

  const navigate = useCallback((path) => {
    window.location.hash = path
  }, [])

  const healthy = health && health.status === 'ok'

  return (
    <div className="app">
      <header className="topbar">
        <div className="brand">
          <b>TriVerify</b>
          <span>Legal Metrology compliance console</span>
        </div>

        <nav className="nav" aria-label="Main">
          <button
            type="button"
            onClick={() => navigate('/')}
            aria-current={route.name === 'intake' ? 'page' : undefined}
          >
            New case
          </button>
          <button
            type="button"
            onClick={() => navigate('/history')}
            aria-current={route.name === 'history' ? 'page' : undefined}
          >
            History
          </button>

          <div className="health" title={health ? JSON.stringify(health) : 'checking…'}>
            <span className={`dot${healthy ? '' : ' off'}`} aria-hidden="true" />
            {health
              ? healthy
                ? `${health.golden_cases} seeded · ${
                    health.offline_ready ? 'offline ready' : 'network mode'
                  }`
                : 'API unreachable'
              : 'checking…'}
          </div>
        </nav>
      </header>

      <main className="main">
        {route.name === 'intake' ? <IntakePage navigate={navigate} /> : null}
        {route.name === 'history' ? <HistoryPage navigate={navigate} /> : null}
        {route.name === 'case' ? <CasePage caseId={route.caseId} /> : null}
      </main>
    </div>
  )
}
