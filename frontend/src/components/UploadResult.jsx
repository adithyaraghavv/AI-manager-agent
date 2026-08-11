export default function UploadResult({ result, error }) {
  if (error) {
    return (
      <div className="tool-activity tool-activity--error">
        <span className="tool-activity__icon">⚠</span>
        <span className="tool-activity__text">{error}</span>
      </div>
    )
  }

  const versionLabel = result.version_number ? ` — version ${result.version_number}` : ''

  return (
    <div className="tool-activity tool-activity--success">
      <span className="tool-activity__icon">✓</span>
      <span className="tool-activity__text">
        Filed "{result.filename}" under "{result.phase}" for {result.client_name}
        {versionLabel}
        {result.version_number > 1 && ' (previous versions kept, not overwritten)'}
      </span>
    </div>
  )
}
