export default function DeleteResult({ clientName, error }) {
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
      <span className="tool-activity__text">Deleted {clientName} — documents, database record, and files removed</span>
    </div>
  )
}
