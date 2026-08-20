export default function DeleteResult({ clientName, error, cancelled }) {
  if (cancelled) {
    return (
      <div className="tool-activity">
        <div className="tool-activity__summary">
          <span className="tool-activity__icon">⚙</span>
          <span className="tool-activity__text">
            Cancelled — {clientName} was not deleted
          </span>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="tool-activity tool-activity--error">
        <div className="tool-activity__summary">
          <span className="tool-activity__icon">⚠</span>
          <span className="tool-activity__text">{error}</span>
        </div>
      </div>
    );
  }

  return (
    <div className="tool-activity tool-activity--success">
      <div className="tool-activity__summary">
        <span className="tool-activity__icon">✓</span>
        <span className="tool-activity__text">
          Deleted {clientName} — hidden everywhere, kept for a recovery window
          before permanent removal
        </span>
      </div>
    </div>
  );
}
