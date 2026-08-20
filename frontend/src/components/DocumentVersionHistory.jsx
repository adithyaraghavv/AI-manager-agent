import { useEffect, useState } from "react";
import { getDocumentVersions, restoreDocumentVersion } from "../api";

function formatDate(iso) {
  if (!iso) return "";
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? iso : d.toLocaleString();
}

// Inline, expandable version history for one document — shown under a
// search result when "Versions" is clicked. Every past upload is listed,
// oldest first, each downloadable on its own; restoring copies an old
// version's content forward as a brand-new version rather than deleting
// anything, so this list only ever grows.
export default function DocumentVersionHistory({ clientName, docType }) {
  const [versions, setVersions] = useState(null);
  const [error, setError] = useState(null);
  const [restoringVersion, setRestoringVersion] = useState(null);
  const [restoreName, setRestoreName] = useState("");

  useEffect(() => {
    let cancelled = false;
    getDocumentVersions(clientName, docType)
      .then((data) => {
        if (!cancelled) setVersions(data);
      })
      .catch((err) => {
        if (!cancelled) setError(err.message);
      });
    return () => {
      cancelled = true;
    };
  }, [clientName, docType]);

  async function handleRestore(versionNumber) {
    setRestoringVersion(versionNumber);
    setError(null);
    try {
      await restoreDocumentVersion(
        clientName,
        docType,
        versionNumber,
        restoreName,
      );
      const fresh = await getDocumentVersions(clientName, docType);
      setVersions(fresh);
    } catch (err) {
      setError(err.message);
    } finally {
      setRestoringVersion(null);
    }
  }

  if (error)
    return <div className="doc-versions doc-versions--error">{error}</div>;
  if (versions === null)
    return (
      <div className="doc-versions doc-versions__loading">
        Loading versions…
      </div>
    );

  const latest = versions.length
    ? versions[versions.length - 1].version_number
    : null;

  return (
    <div className="doc-versions">
      <input
        className="doc-versions__name-input"
        value={restoreName}
        onChange={(e) => setRestoreName(e.target.value)}
        placeholder="Your name (optional, used if you restore a version)"
      />
      <ul className="doc-versions__list">
        {versions.map((v) => (
          <li key={v.version_number} className="doc-versions__item">
            <div className="doc-versions__item-main">
              <span className="doc-versions__badge">v{v.version_number}.0</span>
              <span className="doc-versions__meta">
                {formatDate(v.uploaded_at)}
                {v.uploaded_by ? ` · ${v.uploaded_by}` : ""}
              </span>
              {v.comment && (
                <div className="doc-versions__comment">{v.comment}</div>
              )}
            </div>
            <div className="doc-versions__item-actions">
              <a
                href={v.download_url}
                download
                className="doc-versions__download"
              >
                Download
              </a>
              {v.version_number !== latest && (
                <button
                  className="doc-versions__restore"
                  onClick={() => handleRestore(v.version_number)}
                  disabled={restoringVersion !== null}
                >
                  {restoringVersion === v.version_number
                    ? "Restoring…"
                    : "Restore"}
                </button>
              )}
            </div>
          </li>
        ))}
      </ul>
    </div>
  );
}
