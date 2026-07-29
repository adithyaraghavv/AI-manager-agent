import { useEffect, useState } from 'react'
import { checkHealth } from './api'
import ChatPanel from './components/ChatPanel'
import UploadPanel from './components/UploadPanel'

export default function App() {
  const [backendUp, setBackendUp] = useState(null)

  useEffect(() => {
    checkHealth().then(setBackendUp)
  }, [])

  return (
    <div className="app">
      <header className="app__header">
        <h1>Marlabs Delivery Assistant</h1>
        <span
          className={`status-dot status-dot--${backendUp ? 'up' : 'down'}`}
          title={backendUp ? 'Backend connected' : 'Backend unreachable'}
        />
      </header>
      <main className="app__main">
        <ChatPanel />
        <UploadPanel />
      </main>
    </div>
  )
}
