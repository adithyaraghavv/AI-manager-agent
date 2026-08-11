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
  const showDownload = name === 'request_template' && result.allowed && result.download_url
  const showVersionList = name === 'get_document_versions' && result.found && result.versions?.length > 0

  return (
    <div className="tool-activity">
      <div className="tool-activity__summary">
        <span className="tool-activity__icon">⚙</span>
        <span className="tool-activity__text">{summarize(name, result)}</span>
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
