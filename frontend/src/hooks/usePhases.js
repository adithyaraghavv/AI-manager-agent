import { useEffect, useState } from 'react'
import { getPhases } from '../api'

// Shared by every place that needs a picker of valid document types (attach-in-chat,
// standalone upload form) — fetched from the backend, which reads it straight from
// config/sdlc_phase_config.json, so it can never drift out of sync with what the
// gating logic actually accepts.
//
// Module-scope cache — phases don't change at runtime, so one request per browser
// session is enough regardless of how many components mount DocTypeSelect. Storing
// the in-flight promise (not the resolved value) means concurrent mounts share the
// same request instead of racing.
let inflight = null

export function usePhases() {
  const [phases, setPhases] = useState([])
  const [error, setError] = useState(null)

  useEffect(() => {
    if (!inflight) inflight = getPhases()
    let cancelled = false
    inflight
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
