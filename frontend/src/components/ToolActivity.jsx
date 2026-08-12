import { useEffect, useState } from 'react'

// Present-continuous phrasing shown briefly before settling on the final
// result — same idea as Claude/ChatGPT's transient "Searching…" state, so a
// tool call reads as something actively happening rather than an instant,
// silent fact appearing on screen.
function inProgressPhrase(name, result) {
  switch (name) {
    case 'get_client_status':
      return `Checking status for "${result.client_name}"…`
    case 'request_template':
      return 'Checking template availability…'
    case 'list_phases':
      return 'Listing project phases…'
    case 'get_document_versions':
      return 'Looking up document versions…'
    case 'get_document_location':
      return 'Looking up where it’s stored…'
    case 'search_document_types':
      return `Searching document types for "${result.query}"…`
    case 'propose_delete_client':
      return `Looking up ${result.client_name}…`
    default:
      return 'Working…'
  }
}

function summarize(name, result) {
  switch (name) {
    case 'get_client_status':
      // Rendered as a StatusCard instead — this text is only a fallback
      // (e.g. if `phases` is ever missing from an older/mocked result).
      return `Checked status for "${result.client_name}"`
    case 'request_template':
      return result.allowed
        ? `Template "${result.filename}" is available`
        : `Template request blocked: ${result.reason}`
    case 'list_phases':
      return `Listed ${result.phases?.length ?? 0} project phases`
    case 'get_document_versions':
      if (!result.found) return `No document on file: ${result.reason}`
      return `Found ${result.versions?.length ?? 0} version${result.versions?.length === 1 ? '' : 's'} of "${result.doc_type}" for ${result.client_name}`
    case 'get_document_location':
      return result.found
        ? `Located "${result.doc_type}" for ${result.client_name}`
        : `No document on file: ${result.reason}`
    case 'search_document_types':
      if (result.count === 0) return `No document type matches "${result.query}"`
      if (result.count === 1) return `Found 1 matching document type for "${result.query}"`
      return `Found ${result.count} matching document types for "${result.query}"`
    case 'propose_delete_client':
      return result.found
        ? `Looked up "${result.client_name}" — ${result.phases_complete}/${result.total_phases} phases complete, ${result.document_count} documents filed`
        : `No client named "${result.client_name}" found`
    default:
      return name
  }
}

function StatusCard({ result }) {
  const phases = result.phases ?? []
  const completeCount = phases.filter((p) => p.complete).length
  const blocked = phases.find((p) => !p.complete)
  const pct = phases.length ? Math.round((completeCount / phases.length) * 100) : 0

  return (
    <div className="status-card">
      <div className="status-card__header">
        <span className="status-card__title">{result.client_name}</span>
        <span className={`status-card__badge${blocked ? '' : ' status-card__badge--good'}`}>
          {completeCount}/{phases.length} phases
        </span>
      </div>
      <div className="status-card__bar">
        <div className="status-card__bar-fill" style={{ width: `${pct}%` }} />
      </div>
      {blocked ? (
        <div className="status-card__detail">
          Blocked at <strong>{blocked.phase}</strong> — missing {blocked.missing_documents.join(', ')}
        </div>
      ) : (
        <div className="status-card__detail status-card__detail--good">All phases complete</div>
      )}
    </div>
  )
}

function PathCard({ folderPath }) {
  const [copied, setCopied] = useState(false)

  async function handleCopy() {
    try {
      await navigator.clipboard.writeText(folderPath)
      setCopied(true)
      setTimeout(() => setCopied(false), 1500)
    } catch {
      // Clipboard unavailable — the path is still visible to copy by hand.
    }
  }

  return (
    <div className="path-card">
      <span className="path-card__icon" aria-hidden="true">
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none">
          <path
            d="M3 7a2 2 0 012-2h4l2 2h8a2 2 0 012 2v8a2 2 0 01-2 2H5a2 2 0 01-2-2V7z"
            stroke="currentColor"
            strokeWidth="1.6"
            strokeLinejoin="round"
          />
        </svg>
      </span>
      <code className="path-card__path">{folderPath}</code>
      <button type="button" className="path-card__copy" onClick={handleCopy}>
        {copied ? 'Copied' : 'Copy'}
      </button>
    </div>
  )
}

function FileCard({ title, badge, meta, comment, href }) {
  return (
    <a className="file-card" href={href} download>
      <span className="file-card__icon" aria-hidden="true">
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none">
          <path
            d="M7 3h7l5 5v13a1 1 0 01-1 1H7a1 1 0 01-1-1V4a1 1 0 011-1z"
            stroke="currentColor"
            strokeWidth="1.6"
            strokeLinejoin="round"
          />
          <path d="M14 3v5h5" stroke="currentColor" strokeWidth="1.6" strokeLinejoin="round" />
        </svg>
      </span>
      <span className="file-card__body">
        <span className="file-card__title-row">
          <span className="file-card__title">{title}</span>
          {badge && <span className="file-card__badge">{badge}</span>}
        </span>
        {meta && <span className="file-card__meta">{meta}</span>}
        {comment && <span className="file-card__comment">{comment}</span>}
      </span>
      <span className="file-card__btn">
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" aria-hidden="true">
          <path
            d="M12 4v11m0 0l-4-4m4 4l4-4M5 19h14"
            stroke="currentColor"
            strokeWidth="1.8"
            strokeLinecap="round"
            strokeLinejoin="round"
          />
        </svg>
        Download
      </span>
    </a>
  )
}

export default function ToolActivity({ name, result }) {
  // Every tool result already exists by the time this renders (the whole
  // backend turn has finished), so this delay is purely presentational —
  // it holds on the "…ing" phrasing for a beat before revealing the real
  // outcome, instead of a finished fact just appearing with no sense of
  // something having happened.
  const [settled, setSettled] = useState(false)

  useEffect(() => {
    setSettled(false)
    const timer = setTimeout(() => setSettled(true), 550)
    return () => clearTimeout(timer)
  }, [name, result])

  const showDownload = settled && name === 'request_template' && result.allowed && result.download_url
  const showVersionList = settled && name === 'get_document_versions' && result.found && result.versions?.length > 0
  const showStatusCard = settled && name === 'get_client_status' && Array.isArray(result.phases)
  const showPathCard = settled && name === 'get_document_location' && result.found && result.folder_path

  return (
    <div className="tool-activity">
      <div className="tool-activity__summary">
        <span className={`tool-activity__icon${settled ? '' : ' tool-activity__icon--spin'}`}>
          {settled ? '⚙' : '◌'}
        </span>
        <span className="tool-activity__text">{settled ? summarize(name, result) : inProgressPhrase(name, result)}</span>
      </div>
      {showStatusCard && <StatusCard result={result} />}
      {showPathCard && <PathCard folderPath={result.folder_path} />}
      {showDownload && (
        <div className="file-card-list">
          <FileCard title={result.filename} href={result.download_url} />
        </div>
      )}
      {showVersionList && (
        <div className="file-card-list">
          {result.versions.map((v) => (
            <FileCard
              key={v.version_number}
              title={result.doc_type}
              badge={`v${v.version_number}.0`}
              meta={v.uploaded_by ? `Uploaded by ${v.uploaded_by}` : 'Uploaded'}
              comment={v.comment}
              href={v.download_url}
            />
          ))}
        </div>
      )}
    </div>
  )
}
