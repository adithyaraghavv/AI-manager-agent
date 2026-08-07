import { useState } from 'react'
import { searchDocuments } from '../api'

// Debounced so typing doesn't fire a request per keystroke — waits for a
// short pause before actually searching.
const DEBOUNCE_MS = 350

export default function DocumentSearch() {
  const [query, setQuery] = useState('')
  const [results, setResults] = useState(null)
  const [searching, setSearching] = useState(false)
  const [error, setError] = useState(null)

  function handleChange(e) {
    const value = e.target.value
    setQuery(value)

    clearTimeout(handleChange._timer)
    if (!value.trim()) {
      setResults(null)
      setError(null)
      return
    }

    handleChange._timer = setTimeout(async () => {
      setSearching(true)
      setError(null)
      try {
        const data = await searchDocuments(value)
        setResults(data)
      } catch (err) {
        setError(err.message)
      } finally {
        setSearching(false)
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
            results.map((r, i) => (
              <a key={i} className="doc-search__result" href={r.download_url} download>
                <div>
                  <div className="doc-search__result-name">{r.filename}</div>
                  <div className="doc-search__result-meta">
                    {r.client_name} · {r.doc_type} · {r.phase_name}
                  </div>
                </div>
                <span className="doc-search__result-download">Download</span>
              </a>
            ))
          )}
        </div>
      )}
    </div>
  )
}
