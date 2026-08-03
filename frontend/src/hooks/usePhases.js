import { useEffect, useState } from 'react'
import { getPhases } from '../api'

// Shared by every place that needs a picker of valid document types (attach-in-chat,
// standalone upload form) — fetched from the backend, which reads it straight from
// config/sdlc_phase_config.json, so it can never drift out of sync with what the
// gating logic actually accepts.
export function usePhases() {
  const [phases, setPhases] = useState([])
  const [error, setError] = useState(null)

  useEffect(() => {
    let cancelled = false
    getPhases()
      .then((data) => {
        if (!cancelled) setPhases(data)
      })
      .catch((err) => {
        if (!cancelled) setError(err.message)
      })
    return () => {
      cancelled = true
    }
  }, [])

  return { phases, error }
}
