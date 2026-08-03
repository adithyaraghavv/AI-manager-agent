export default function UploadResult({ result, error }) {
  if (error) {
    return (
      <div className="tool-activity tool-activity--error">
        <span className="tool-activity__icon">⚠</span>
        <span className="tool-activity__text">{error}</span>
      </div>
    )
  }

  return (
    <div className="tool-activity tool-activity--success">
      <span className="tool-activity__icon">✓</span>
      <span className="tool-activity__text">
        Filed "{result.filename}" under "{result.phase}" for {result.client_name}
      </span>
    </div>
  )
}
