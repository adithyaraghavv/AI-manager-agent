import { useEffect, useState } from 'react'
import { getClientStatuses } from '../api'

function ProgressMeter({ complete, total, isStale }) {
  const pct = total > 0 ? Math.round((complete / total) * 100) : 0
  // Meter fill carries severity: warning color if the client is stuck, accent otherwise.
  const fillClass = isStale ? 'progress-meter__fill--warning' : 'progress-meter__fill--accent'
  return (
    <div className="progress-meter">
      <div className="progress-meter__track">
        <div className={`progress-meter__fill ${fillClass}`} style={{ width: `${pct}%` }} />
      </div>
      <span className="progress-meter__label">
        {complete}/{total} phases
      </span>
    </div>
  )
}

function StatusBadge({ isStale, daysSinceActivity, currentPhase }) {
  if (currentPhase === null) {
    return (
      <span className="status-badge status-badge--good">
        <span className="status-badge__icon" aria-hidden="true">✓</span> Complete
      </span>
    )
  }
  if (isStale) {
    const days = daysSinceActivity !== null ? Math.floor(daysSinceActivity) : '?'
    return (
      <span className="status-badge status-badge--warning">
        <span className="status-badge__icon" aria-hidden="true">⚠</span> Stale ({days}d)
      </span>
    )
  }
  return (
    <span className="status-badge status-badge--neutral">
      <span aria-hidden="true">●</span> On track
    </span>
  )
}

export default function Dashboard() {
  const [clients, setClients] = useState(null)
  const [error, setError] = useState(null)

  useEffect(() => {
    let cancelled = false
    getClientStatuses()
      .then((data) => {
        if (!cancelled) setClients(data)
      })
      .catch((err) => {
        if (!cancelled) setError(err.message)
      })
    return () => {
      cancelled = true
    }
  }, [])

  const staleCount = clients?.filter((c) => c.is_stale).length ?? 0

  return (
    <div className="dashboard">
      <div className="dashboard__header">
        <h2>Client Portfolio</h2>
        {clients && (
          <span className="dashboard__summary">
            {clients.length} client{clients.length === 1 ? '' : 's'}
            {staleCount > 0 && (
              <>
                {' · '}
                <span className="dashboard__summary-stale">{staleCount} stale</span>
              </>
            )}
          </span>
        )}
      </div>

      {error && <div className="chat-panel__error">{error}</div>}
      {!error && clients === null && <div className="dashboard__empty">Loading…</div>}
      {clients?.length === 0 && (
        <div className="dashboard__empty">No clients yet — ask the assistant for a template to get started.</div>
      )}

      {clients?.length > 0 && (
        <table className="dashboard__table">
          <thead>
            <tr>
              <th>Client</th>
              <th>Progress</th>
              <th>Current phase</th>
              <th>Status</th>
            </tr>
          </thead>
          <tbody>
            {clients.map((c) => (
              <tr key={c.client_name}>
                <td className="dashboard__client-name">{c.client_name}</td>
                <td>
                  <ProgressMeter complete={c.phases_complete} total={c.total_phases} isStale={c.is_stale} />
                </td>
                <td>
                  {c.current_phase ?? <span className="dashboard__muted">—</span>}
                  {c.missing_documents.length > 0 && (
                    <div className="dashboard__missing">
                      Missing: {c.missing_documents.join(', ')}
                    </div>
                  )}
                </td>
                <td>
                  <StatusBadge
                    isStale={c.is_stale}
                    daysSinceActivity={c.days_since_activity}
                    currentPhase={c.current_phase}
                  />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  )
}
