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
    case 'propose_delete_client':
      return `Looking up ${result.client_name}…`
    default:
      return 'Working…'
  }
}

function summarize(name, result) {
  switch (name) {
    case 'get_client_status': {
      const blocked = result.phases?.find((p) => !p.complete)
      return blocked
        ? `Checked status for "${result.client_name}" — blocked at "${blocked.phase}" (missing: ${blocked.missing_documents.join(', ')})`
        : `Checked status for "${result.client_name}" — all phases complete`
    }
    case 'request_template':
      return result.allowed
        ? `Template "${result.filename}" is available`
        : `Template request blocked: ${result.reason}`
    case 'list_phases':
      return `Listed ${result.phases?.length ?? 0} project phases`
    case 'get_document_versions':
      if (!result.found) return `No document on file: ${result.reason}`
      return `Found ${result.versions?.length ?? 0} version${result.versions?.length === 1 ? '' : 's'} of "${result.doc_type}" for ${result.client_name}`
    case 'propose_delete_client':
      return result.found
        ? `Looked up "${result.client_name}" — ${result.phases_complete}/${result.total_phases} phases complete, ${result.document_count} documents filed`
        : `No client named "${result.client_name}" found`
    default:
      return name
  }
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

  return (
    <div className="tool-activity">
      <div className="tool-activity__summary">
        <span className={`tool-activity__icon${settled ? '' : ' tool-activity__icon--spin'}`}>
          {settled ? '⚙' : '◌'}
        </span>
        <span className="tool-activity__text">{settled ? summarize(name, result) : inProgressPhrase(name, result)}</span>
      </div>
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
