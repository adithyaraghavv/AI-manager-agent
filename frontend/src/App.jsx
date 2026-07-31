import { useEffect, useState } from 'react'
import { checkHealth } from './api'
import ChatPanel from './components/ChatPanel'
import Dashboard from './components/Dashboard'
import UploadPanel from './components/UploadPanel'

export default function App() {
  const [backendUp, setBackendUp] = useState(null)
  const [view, setView] = useState('chat')

  useEffect(() => {
    checkHealth().then(setBackendUp)
  }, [])

  return (
    <div className="app">
      <header className="app__header">
        <h1>Marlabs Delivery Assistant</h1>
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
