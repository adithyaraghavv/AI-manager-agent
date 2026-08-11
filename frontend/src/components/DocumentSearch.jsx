import { useRef, useState } from 'react'
import { searchDocuments } from '../api'
import DocumentVersionHistory from './DocumentVersionHistory'

// Debounced so typing doesn't fire a request per keystroke — waits for a
// short pause before actually searching.
const DEBOUNCE_MS = 350

export default function DocumentSearch() {
  const [query, setQuery] = useState('')
  const [results, setResults] = useState(null)
  const [searching, setSearching] = useState(false)
  const [error, setError] = useState(null)
  const [expandedKey, setExpandedKey] = useState(null)
  const timerRef = useRef(null)
  const latestQueryRef = useRef('')

  function toggleVersions(key) {
    setExpandedKey((current) => (current === key ? null : key))
  }

  function handleChange(e) {
    const value = e.target.value
    setQuery(value)
    latestQueryRef.current = value

    clearTimeout(timerRef.current)
    if (!value.trim()) {
      setResults(null)
      setError(null)
      setSearching(false)
      return
    }

    timerRef.current = setTimeout(async () => {
      setSearching(true)
      setError(null)
      try {
        const data = await searchDocuments(value)
        // Ignore stale responses — the box may have been cleared or changed
        // to something else while this request was in flight.
        if (latestQueryRef.current !== value) return
        setResults(data)
      } catch (err) {
        if (latestQueryRef.current !== value) return
        setError(err.message)
      } finally {
        if (latestQueryRef.current === value) setSearching(false)
      }
    }, DEBOUNCE_MS)
  }

  return (
    <div className="doc-search">
      <div className="doc-search__input-wrap">
        <svg width="15" height="15" viewBox="0 0 24 24" fill="none" aria-hidden="true">
          <circle cx="11" cy="11" r="8" stroke="currentColor" strokeWidth="2" />
          <line x1="21" y1="21" x2="16.65" y2="16.65" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
        </svg>
        <input
          type="text"
          className="doc-search__input"
          placeholder="Search documents by client, type, or filename…"
          value={query}
          onChange={handleChange}
        />
      </div>

      {searching && <div className="doc-search__status">Searching…</div>}
      {error && <div className="doc-search__status doc-search__status--error">{error}</div>}
      {!searching && !error && results !== null && (
        <div className="doc-search__results">
          {results.length === 0 ? (
            <div className="doc-search__status">No documents match "{query}"</div>
          ) : (
            results.map((r, i) => {
              const key = `${r.client_name}::${r.doc_type}`
              return (
                <div key={i} className="doc-search__result-wrap">
                  <div className="doc-search__result">
                    <a className="doc-search__result-link" href={r.download_url} download>
                      <div className="doc-search__result-name">{r.filename}</div>
                      <div className="doc-search__result-meta">
                        {r.client_name} · {r.doc_type} · {r.phase_name}
                      </div>
                    </a>
                    <button
                      type="button"
                      className="doc-search__result-versions-toggle"
                      onClick={() => toggleVersions(key)}
                    >
                      {expandedKey === key ? 'Hide versions' : 'Versions'}
                    </button>
                  </div>
                  {expandedKey === key && (
                    <DocumentVersionHistory clientName={r.client_name} docType={r.doc_type} />
                  )}
                </div>
              )
            })
          )}
        </div>
      )}
    </div>
  )
}
