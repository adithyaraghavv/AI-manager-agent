function relativeTime(iso) {
  const minutes = Math.floor((Date.now() - new Date(iso).getTime()) / 60000)
  if (minutes < 1) return 'just now'
  if (minutes < 60) return `${minutes}m ago`
  const hours = Math.floor(minutes / 60)
  if (hours < 24) return `${hours}h ago`
  const days = Math.floor(hours / 24)
  return days === 1 ? 'yesterday' : `${days}d ago`
}

export default function ChatHistoryMenu({ entries, activeId, onLoad, onDelete, onClose }) {
  return (
    <div className="chat-history-menu">
      <div className="chat-history-menu__header">Recent chats</div>
      {entries.length === 0 ? (
        <div className="chat-history-menu__empty">No saved chats yet</div>
      ) : (
        <ul className="chat-history-menu__list">
          {entries.map((entry) => (
            <li key={entry.id} className={`chat-history-menu__item${entry.id === activeId ? ' chat-history-menu__item--active' : ''}`}>
              <button
                type="button"
                className="chat-history-menu__load"
                onClick={() => {
                  onLoad(entry)
                  onClose()
                }}
              >
                <span className="chat-history-menu__title">{entry.title}</span>
                <span className="chat-history-menu__time">{relativeTime(entry.updatedAt)}</span>
              </button>
              <button
                type="button"
                className="chat-history-menu__delete"
                title="Delete this chat"
                onClick={(e) => {
                  e.stopPropagation()
                  onDelete(entry.id)
                }}
              >
                <svg width="13" height="13" viewBox="0 0 24 24" fill="none" aria-hidden="true">
                  <path d="M18 6L6 18M6 6l12 12" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
                </svg>
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
