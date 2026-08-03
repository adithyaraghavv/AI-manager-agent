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
    default:
      return name
  }
}

export default function ToolActivity({ name, result }) {
  const showDownload = name === 'request_template' && result.allowed && result.download_url

  return (
    <div className="tool-activity">
      <span className="tool-activity__icon">⚙</span>
      <span className="tool-activity__text">{summarize(name, result)}</span>
      {showDownload && (
        <a className="tool-activity__download" href={result.download_url} download>
          Download {result.filename}
        </a>
      )}
    </div>
  )
}
