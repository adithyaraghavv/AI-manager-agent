import { useEffect, useState } from "react";
import { getClientStatuses } from "../api";
import DocumentSearch from "./DocumentSearch";

function buildReminderMessage(client) {
  const days =
    client.days_since_activity !== null
      ? Math.floor(client.days_since_activity)
      : "?";
  return (
    `Hi ${client.client_name} team,\n\n` +
    `Following up on the ${client.current_phase} phase — we're still waiting on: ` +
    `${client.missing_documents.join(", ")}.\n\n` +
    `It's been ${days} day${days === 1 ? "" : "s"} since we last received an update. ` +
    `Please let us know if you need anything from our side to move this forward.\n\n` +
    `Thanks,`
  );
}

function CopyReminderButton({ client }) {
  const [copied, setCopied] = useState(false);

  const handleClick = async () => {
    const message = buildReminderMessage(client);
    try {
      await navigator.clipboard.writeText(message);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch {
      // Clipboard API can be unavailable (older browsers, non-HTTPS) — fail
      // quietly rather than throwing in the manager's face over a copy button.
    }
  };

  return (
    <button type="button" className="dashboard__copy-btn" onClick={handleClick}>
      {copied ? "Copied ✓" : "Copy reminder"}
    </button>
  );
}

function ProgressMeter({ complete, total, isStale }) {
  const pct = total > 0 ? Math.round((complete / total) * 100) : 0;
  // Meter fill carries severity: warning color if the client is stuck, accent otherwise.
  const fillClass = isStale
    ? "progress-meter__fill--warning"
    : "progress-meter__fill--accent";

  // Starts at 0 and animates up to the real value on mount (CSS transition on
  // width) instead of snapping straight to it — purely cosmetic, no effect
  // on the underlying data.
  const [displayPct, setDisplayPct] = useState(0);
  useEffect(() => {
    const id = requestAnimationFrame(() => setDisplayPct(pct));
    return () => cancelAnimationFrame(id);
  }, [pct]);

  return (
    <div className="progress-meter">
      <div className="progress-meter__track">
        <div
          className={`progress-meter__fill ${fillClass}`}
          style={{ width: `${displayPct}%` }}
        />
      </div>
      <span className="progress-meter__label">
        {complete}/{total} phases
      </span>
    </div>
  );
}

function StatusBadge({ isStale, daysSinceActivity, currentPhase }) {
  if (currentPhase === null) {
    return (
      <span className="status-badge status-badge--good">
        <span className="status-badge__icon" aria-hidden="true">
          ✓
        </span>{" "}
        Complete
      </span>
    );
  }
  if (isStale) {
    const days =
      daysSinceActivity !== null ? Math.floor(daysSinceActivity) : "?";
    return (
      <span className="status-badge status-badge--warning">
        <span className="status-badge__icon" aria-hidden="true">
          ⚠
        </span>{" "}
        Stale ({days}d)
      </span>
    );
  }
  return (
    <span className="status-badge status-badge--neutral">
      <span aria-hidden="true">●</span> On track
    </span>
  );
}

export default function Dashboard() {
  const [clients, setClients] = useState(null);
  const [error, setError] = useState(null);
  const [retryCount, setRetryCount] = useState(0);

  useEffect(() => {
    let cancelled = false;
    setError(null);
    getClientStatuses()
      .then((data) => {
        if (!cancelled) setClients(data);
      })
      .catch((err) => {
        if (!cancelled) setError(err.message);
      });
    return () => {
      cancelled = true;
    };
  }, [retryCount]);

  const staleCount = clients?.filter((c) => c.is_stale).length ?? 0;
  const completeCount = clients?.filter((c) => c.current_phase === null).length ?? 0;
  const onTrackCount = (clients?.length ?? 0) - staleCount - completeCount;

  // Most-overdue-first: stale clients (longest-stale first), then active
  // ones still in progress, then fully complete ones last — nothing left to
  // act on there, so they shouldn't push down clients that actually need
  // attention.
  const sortedClients = clients
    ? [...clients].sort((a, b) => {
        const rank = (c) => (c.is_stale ? 0 : c.current_phase === null ? 2 : 1);
        const rankDiff = rank(a) - rank(b);
        if (rankDiff !== 0) return rankDiff;
        if (a.is_stale) {
          return (b.days_since_activity ?? 0) - (a.days_since_activity ?? 0);
        }
        return 0;
      })
    : clients;

  return (
    <div className="dashboard">
      <div className="dashboard__header">
        <h2>Client Portfolio</h2>
      </div>

      {clients && clients.length > 0 && (
        <div className="dashboard__stats">
          <div className="dashboard__stat-card">
            <span className="dashboard__stat-label">Total Clients</span>
            <span className="dashboard__stat-value">{clients.length}</span>
          </div>
          <div className="dashboard__stat-card">
            <span className="dashboard__stat-label">Stale</span>
            <span className="dashboard__stat-value dashboard__stat-value--warning">
              {staleCount}
            </span>
          </div>
          <div className="dashboard__stat-card">
            <span className="dashboard__stat-label">On Track</span>
            <span className="dashboard__stat-value">{onTrackCount}</span>
          </div>
          <div className="dashboard__stat-card">
            <span className="dashboard__stat-label">Complete</span>
            <span className="dashboard__stat-value dashboard__stat-value--ok">
              {completeCount}
            </span>
          </div>
        </div>
      )}

      <DocumentSearch />

      {error && (
        <div className="dashboard__error">
          <p>
            Couldn't load the client portfolio right now — the backend may be
            unreachable.
          </p>
          <button
            type="button"
            className="dashboard__copy-btn"
            onClick={() => setRetryCount((n) => n + 1)}
          >
            Retry
          </button>
        </div>
      )}
      {!error && clients === null && (
        <div className="dashboard__empty">Loading…</div>
      )}
      {clients?.length === 0 && (
        <div className="dashboard__empty">
          No clients yet — ask the assistant for a template to get started.
        </div>
      )}

      {sortedClients?.length > 0 && (
        <div className="dashboard__table-wrap">
          <table className="dashboard__table">
            <thead>
              <tr>
                <th>Client</th>
                <th>Progress</th>
                <th>Current phase</th>
                <th>Status</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {sortedClients.map((c, i) => (
                <tr
                  key={c.client_name}
                  className="dashboard__row-enter"
                  style={{ animationDelay: `${i * 60}ms` }}
                >
                  <td className="dashboard__client-name">{c.client_name}</td>
                  <td>
                    <ProgressMeter
                      complete={c.phases_complete}
                      total={c.total_phases}
                      isStale={c.is_stale}
                    />
                  </td>
                  <td>
                    {c.current_phase ?? (
                      <span className="dashboard__muted">—</span>
                    )}
                    {c.missing_documents.length > 0 && (
                      <div className="dashboard__missing">
                        Missing:{" "}
                        {c.missing_documents.map((doc, idx) => (
                          <span key={doc}>
                            <span className="dashboard__missing-name">
                              {doc}
                            </span>
                            {idx < c.missing_documents.length - 1 && ", "}
                          </span>
                        ))}
                      </div>
                    )}
                  </td>
                  <td>
                    <StatusBadge
                      isStale={c.is_stale}
                      daysSinceActivity={c.days_since_activity}
                      currentPhase={c.current_phase}
                    />
                  </td>
                  <td>{c.is_stale && <CopyReminderButton client={c} />}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
