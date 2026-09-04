import { useEffect, useState } from "react";

// Present-continuous phrasing shown briefly before settling on the final
// result — same idea as Claude/ChatGPT's transient "Searching…" state, so a
// tool call reads as something actively happening rather than an instant,
// silent fact appearing on screen.
function inProgressPhrase(name, result) {
  switch (name) {
    case "get_client_status":
      return `Checking status for "${result.client_name}"…`;
    case "request_template":
      return "Checking template availability…";
    case "list_phases":
      return "Listing project phases…";
    case "get_document_versions":
      return "Looking up document versions…";
    case "get_document_location":
      return "Looking up where it’s stored…";
    case "search_document_types":
      return `Searching document types for "${result.query}"…`;
    case "propose_delete_client":
      return `Looking up ${result.client_name}…`;
    case "get_sow_summary":
      return `Reading the SOW for "${result.client_name}"…`;
    case "generate_approval_reminder":
      return `Looking up who's responsible for "${result.doc_type}"…`;
    default:
      return "Working…";
  }
}

function summarize(name, result) {
  switch (name) {
    case "get_client_status":
      // Rendered as a StatusCard instead — this text is only a fallback
      // (e.g. if `phases` is ever missing from an older/mocked result).
      return `Checked status for "${result.client_name}"`;
    case "request_template":
      return result.allowed
        ? `Template "${result.filename}" is available`
        : `Template request blocked: ${result.reason}`;
    case "list_phases":
      return `Listed ${result.phases?.length ?? 0} project phases`;
    case "get_document_versions":
      if (!result.found) return `No document on file: ${result.reason}`;
      return `Found ${result.versions?.length ?? 0} version${result.versions?.length === 1 ? "" : "s"} of "${result.doc_type}" for ${result.client_name}`;
    case "get_document_location":
      return result.found
        ? `Located "${result.doc_type}" for ${result.client_name}`
        : `No document on file: ${result.reason}`;
    case "search_document_types":
      if (result.count === 0)
        return `No document type matches "${result.query}"`;
      if (result.count === 1)
        return `Found 1 matching document type for "${result.query}"`;
      return `Found ${result.count} matching document types for "${result.query}"`;
    case "propose_delete_client":
      return result.found
        ? `Looked up "${result.client_name}" — ${result.phases_complete}/${result.total_phases} phases complete, ${result.document_count} documents filed`
        : `No client named "${result.client_name}" found`;
    case "get_sow_summary":
      return result.found
        ? `Pulled SOW summary for "${result.client_name}"`
        : `Couldn't read the SOW: ${result.reason}`;
    case "generate_approval_reminder":
      return result.found
        ? `Found who's responsible for "${result.doc_type}" — reminder ready to copy`
        : `Couldn't find who's responsible: ${result.reason}`;
    default:
      return name;
  }
}

function ReminderCard({ approver, message }) {
  const [copied, setCopied] = useState(false);

  async function handleCopy() {
    try {
      await navigator.clipboard.writeText(message);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch {
      // Clipboard unavailable — the message is still visible to copy by hand.
    }
  }

  return (
    <div className="reminder-card">
      <div className="reminder-card__header">
        <span className="reminder-card__to">Addressed to: {approver}</span>
        <button
          type="button"
          className="reminder-card__copy"
          onClick={handleCopy}
        >
          {copied ? "Copied" : "Copy"}
        </button>
      </div>
      <pre className="reminder-card__body">{message}</pre>
    </div>
  );
}

function PathCard({ folderPath, webUrl }) {
  const [copied, setCopied] = useState(false);

  async function handleCopy() {
    try {
      await navigator.clipboard.writeText(folderPath);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
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
        {copied ? "Copied" : "Copy"}
      </button>
      {webUrl && (
        <a
          className="path-card__open"
          href={webUrl}
          target="_blank"
          rel="noopener noreferrer"
        >
          Open in SharePoint
        </a>
      )}
    </div>
  );
}

function phasePercent(phase) {
  const total = phase.completed_documents.length + phase.missing_documents.length;
  if (total === 0) return 100;
  return Math.round((phase.completed_documents.length / total) * 100);
}

function ProjectProgressBar({ percent }) {
  const tone =
    percent === 100 ? "complete" : percent === 0 ? "blocked" : "partial";
  return (
    <div className="status-progress">
      <div className="status-progress__bar">
        <div
          className={`status-progress__fill status-progress__fill--${tone}`}
          style={{ width: `${percent}%` }}
        />
      </div>
      <span className={`status-progress__pct status-progress__pct--${tone}`}>
        {percent}%
      </span>
    </div>
  );
}

function DocumentBadge({ doc, kind }) {
  return (
    <span className={`status-doc-badge status-doc-badge--${kind}`}>
      <span className="status-doc-badge__icon" aria-hidden="true">
        {kind === "done" ? "✓" : "!"}
      </span>
      {doc}
    </span>
  );
}

function StatusSummaryCards({ phases }) {
  const totalPhases = phases.length;
  const completedPhases = phases.filter((p) => p.complete).length;
  const activePhase = phases.find((p) => !p.complete);
  const missingCount = phases.reduce(
    (sum, p) => sum + p.missing_documents.length,
    0,
  );

  return (
    <div className="status-summary">
      <div className="status-summary__card">
        <span className="status-summary__label">Total Phases</span>
        <span className="status-summary__value">{totalPhases}</span>
      </div>
      <div className="status-summary__card">
        <span className="status-summary__label">Completed Phases</span>
        <span className="status-summary__value status-summary__value--ok">
          {completedPhases}
        </span>
      </div>
      <div className="status-summary__card">
        <span className="status-summary__label">Active Phase</span>
        <span className="status-summary__value status-summary__value--text">
          {activePhase ? activePhase.phase : "None — all complete"}
        </span>
      </div>
      <div className="status-summary__card">
        <span className="status-summary__label">Missing Documents</span>
        <span
          className={`status-summary__value${missingCount > 0 ? " status-summary__value--danger" : " status-summary__value--ok"}`}
        >
          {missingCount}
        </span>
      </div>
    </div>
  );
}

function PhaseStatusTable({ phases }) {
  return (
    <div className="status-table-wrap">
      <table className="status-table">
        <thead>
          <tr>
            <th>Phase</th>
            <th>Progress</th>
            <th>Completed Documents</th>
            <th>Missing Documents</th>
          </tr>
        </thead>
        <tbody>
          {phases.map((phase) => {
            const percent = phasePercent(phase);
            const statusIcon = phase.complete ? "✅" : percent === 0 ? "❌" : "⚠";
            const statusLabel = phase.complete
              ? "Complete"
              : percent === 0
                ? "Blocked"
                : "In Progress";
            return (
              <tr
                key={phase.phase}
                className={phase.complete ? "status-table__row--complete" : ""}
              >
                <td className="status-table__phase">
                  <span className="status-table__phase-name">{phase.phase}</span>
                  <span
                    className={`status-table__badge${
                      phase.complete
                        ? " status-table__badge--complete"
                        : percent === 0
                          ? " status-table__badge--blocked"
                          : " status-table__badge--pending"
                    }`}
                  >
                    {statusIcon} {statusLabel}
                  </span>
                </td>
                <td>
                  <ProjectProgressBar percent={percent} />
                </td>
                <td>
                  {phase.completed_documents.length > 0 ? (
                    <div className="status-table__chips">
                      {phase.completed_documents.map((doc) => (
                        <DocumentBadge key={doc} doc={doc} kind="done" />
                      ))}
                    </div>
                  ) : (
                    <span className="status-table__none">None</span>
                  )}
                </td>
                <td>
                  {phase.missing_documents.length > 0 ? (
                    <div className="status-table__chips">
                      {phase.missing_documents.map((doc) => (
                        <DocumentBadge key={doc} doc={doc} kind="missing" />
                      ))}
                    </div>
                  ) : (
                    <span className="status-table__none status-table__none--good">
                      No Missing Documents
                    </span>
                  )}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

function StatusTable({ phases }) {
  return (
    <div className="status-dashboard">
      <StatusSummaryCards phases={phases} />
      <PhaseStatusTable phases={phases} />
    </div>
  );
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
          <path
            d="M14 3v5h5"
            stroke="currentColor"
            strokeWidth="1.6"
            strokeLinejoin="round"
          />
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
        <svg
          width="14"
          height="14"
          viewBox="0 0 24 24"
          fill="none"
          aria-hidden="true"
        >
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
  );
}

export default function ToolActivity({ name, result }) {
  // Every tool result already exists by the time this renders (the whole
  // backend turn has finished), so this delay is purely presentational —
  // it holds on the "…ing" phrasing for a beat before revealing the real
  // outcome, instead of a finished fact just appearing with no sense of
  // something having happened.
  const [settled, setSettled] = useState(false);

  useEffect(() => {
    setSettled(false);
    const timer = setTimeout(() => setSettled(true), 550);
    return () => clearTimeout(timer);
    // Depend on a stringified snapshot, not `result` itself: the caller
    // re-parses `result` from JSON on every render, so it's a fresh object
    // reference every time even when nothing actually changed — an
    // unrelated parent re-render (e.g. typing in the chat input) would
    // otherwise reset an already-settled card back to its "…ing" spinner
    // state on every keystroke. Strings compare by value, so this only
    // re-fires when the tool result's actual content changes.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [name, JSON.stringify(result)]);

  const showDownload =
    settled &&
    name === "request_template" &&
    result.allowed &&
    result.download_url;
  const showVersionList =
    settled &&
    name === "get_document_versions" &&
    result.found &&
    result.versions?.length > 0;
  const showPathCard =
    settled &&
    name === "get_document_location" &&
    result.found &&
    result.folder_path;
  const showReminderCard =
    settled && name === "generate_approval_reminder" && result.found;
  const showStatusTable =
    settled &&
    name === "get_client_status" &&
    Array.isArray(result.phases) &&
    result.phases.length > 0 &&
    result.phases.every((p) => Array.isArray(p.required_documents));

  return (
    <div className="tool-activity">
      <div className="tool-activity__summary">
        <span
          className={`tool-activity__icon${settled ? "" : " tool-activity__icon--spin"}`}
        >
          {settled ? "⚙" : "◌"}
        </span>
        <span className="tool-activity__text">
          {settled ? summarize(name, result) : inProgressPhrase(name, result)}
        </span>
      </div>
      {showStatusTable && <StatusTable phases={result.phases} />}
      {showPathCard && (
        <PathCard folderPath={result.folder_path} webUrl={result.web_url} />
      )}
      {showReminderCard && (
        <ReminderCard
          approver={result.approver}
          message={result.reminder_message}
        />
      )}
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
              meta={v.uploaded_by ? `Uploaded by ${v.uploaded_by}` : "Uploaded"}
              comment={v.comment}
              href={v.download_url}
            />
          ))}
        </div>
      )}
    </div>
  );
}
