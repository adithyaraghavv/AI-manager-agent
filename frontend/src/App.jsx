import { useEffect, useState } from 'react'
import { checkHealth } from './api'
import marlabsLogo from './assets/marlabs-logo.png'
import ChatPanel from './components/ChatPanel'
import Dashboard from './components/Dashboard'
import UploadPanel from './components/UploadPanel'

const HERO_COPY = {
  chat: {
    title: 'Delivery Assistant',
    subtitle: 'Request templates, check client status, and file completed documents — all phase-gated automatically.',
  },
  dashboard: {
    title: 'Client Portfolio',
    subtitle: 'Every client’s phase progress at a glance, with stale clients flagged automatically.',
  },
}

export default function App() {
  const [backendUp, setBackendUp] = useState(null)
  const [view, setView] = useState('chat')

  useEffect(() => {
    checkHealth().then(setBackendUp)
  }, [])

  const hero = HERO_COPY[view]

  return (
    <div className="app">
      <header className="app__header">
        <img src={marlabsLogo} alt="Marlabs" className="app__logo" />
        <nav className="app__tabs">
          <button
            className={`app__tab ${view === 'chat' ? 'app__tab--active' : ''}`}
            onClick={() => setView('chat')}
          >
            Chat
          </button>
          <button
            className={`app__tab ${view === 'dashboard' ? 'app__tab--active' : ''}`}
            onClick={() => setView('dashboard')}
          >
            Dashboard
          </button>
        </nav>
        <span
          className={`status-dot status-dot--${backendUp ? 'up' : 'down'}`}
          title={backendUp ? 'Backend connected' : 'Backend unreachable'}
        />
      </header>
      <div className="app__hero">
        <h1>{hero.title}</h1>
        <p>{hero.subtitle}</p>
      </div>
      <main className="app__main">
        {view === 'chat' ? (
          <>
            <ChatPanel />
            <UploadPanel />
          </>
        ) : (
          <Dashboard />
        )}
      </main>
    </div>
  )
}
