import { useEffect, useRef, useState } from "react";

const DAY_MS = 24 * 60 * 60 * 1000;

// Buckets are computed fresh on every render off `Date.now()` — cheap for a
// list capped at 30 entries, and means a chat correctly slides from "Today"
// to "Yesterday" etc. just by the sidebar re-rendering, no timers needed.
function groupByDate(entries) {
  const now = new Date();
  const startOfToday = new Date(
    now.getFullYear(),
    now.getMonth(),
    now.getDate(),
  ).getTime();

  const groups = {
    Today: [],
    Yesterday: [],
    "Previous 7 Days": [],
    "Previous 30 Days": [],
    Older: [],
  };
  for (const entry of entries) {
    const age = startOfToday - new Date(entry.updatedAt).setHours(0, 0, 0, 0);
    if (age < DAY_MS) groups.Today.push(entry);
    else if (age < 2 * DAY_MS) groups.Yesterday.push(entry);
    else if (age < 8 * DAY_MS) groups["Previous 7 Days"].push(entry);
    else if (age < 31 * DAY_MS) groups["Previous 30 Days"].push(entry);
    else groups.Older.push(entry);
  }
  return Object.entries(groups).filter(([, items]) => items.length > 0);
}

function SidebarItem({ entry, active, onLoad, onDelete, onRename }) {
  const [menuOpen, setMenuOpen] = useState(false);
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(entry.title);
  const menuRef = useRef(null);
  const inputRef = useRef(null);

  useEffect(() => {
    if (!menuOpen) return;
    function handleClickOutside(e) {
      if (menuRef.current && !menuRef.current.contains(e.target))
        setMenuOpen(false);
    }
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, [menuOpen]);

  useEffect(() => {
    if (editing) inputRef.current?.focus();
  }, [editing]);

  function commitRename() {
    setEditing(false);
    if (draft.trim() && draft.trim() !== entry.title)
      onRename(entry.id, draft.trim());
    else setDraft(entry.title);
  }

  if (editing) {
    return (
      <li className="sidebar__item">
        <input
          ref={inputRef}
          className="sidebar__rename-input"
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          onBlur={commitRename}
          onKeyDown={(e) => {
            if (e.key === "Enter") commitRename();
            if (e.key === "Escape") {
              setDraft(entry.title);
              setEditing(false);
            }
          }}
        />
      </li>
    );
  }

  return (
    <li className={`sidebar__item${active ? " sidebar__item--active" : ""}`}>
      <button
        type="button"
        className="sidebar__item-load"
        onClick={() => onLoad(entry)}
      >
        <span className="sidebar__item-title">{entry.title}</span>
      </button>
      <div className="sidebar__item-menu-wrap" ref={menuRef}>
        <button
          type="button"
          className="sidebar__item-menu-btn"
          title="Chat options"
          onClick={(e) => {
            e.stopPropagation();
            setMenuOpen((v) => !v);
          }}
        >
          <svg
            width="15"
            height="15"
            viewBox="0 0 24 24"
            fill="currentColor"
            aria-hidden="true"
          >
            <circle cx="5" cy="12" r="2" />
            <circle cx="12" cy="12" r="2" />
            <circle cx="19" cy="12" r="2" />
          </svg>
          <span className="sr-only">Chat options</span>
        </button>
        {menuOpen && (
          <div className="sidebar__item-menu">
            <button
              type="button"
              className="sidebar__item-menu-option"
              onClick={() => {
                setMenuOpen(false);
                setEditing(true);
              }}
            >
              Rename
            </button>
            <button
              type="button"
              className="sidebar__item-menu-option sidebar__item-menu-option--danger"
              onClick={() => {
                setMenuOpen(false);
                onDelete(entry.id);
              }}
            >
              Delete
            </button>
          </div>
        )}
      </div>
    </li>
  );
}

export default function Sidebar({
  entries,
  activeId,
  onNewChat,
  onLoad,
  onDelete,
  onRename,
  open,
  onClose,
}) {
  const groups = groupByDate(entries);

  return (
    <>
      {open && <div className="sidebar__backdrop" onClick={onClose} />}
      <aside className={`sidebar${open ? " sidebar--open" : ""}`}>
        <div className="sidebar__top">
          <button
            type="button"
            className="sidebar__new-chat"
            onClick={() => {
              onNewChat();
              onClose?.();
            }}
          >
            <svg
              width="16"
              height="16"
              viewBox="0 0 24 24"
              fill="none"
              aria-hidden="true"
            >
              <path
                d="M12 5v14M5 12h14"
                stroke="currentColor"
                strokeWidth="2.2"
                strokeLinecap="round"
              />
            </svg>
            New chat
          </button>
        </div>

        <div className="sidebar__history">
          {entries.length === 0 ? (
            <div className="sidebar__empty">No saved chats yet</div>
          ) : (
            groups.map(([label, items]) => (
              <div className="sidebar__group" key={label}>
                <div className="sidebar__group-label">{label}</div>
                <ul className="sidebar__list">
                  {items.map((entry) => (
                    <SidebarItem
                      key={entry.id}
                      entry={entry}
                      active={entry.id === activeId}
                      onLoad={(e) => {
                        onLoad(e);
                        onClose?.();
                      }}
                      onDelete={onDelete}
                      onRename={onRename}
                    />
                  ))}
                </ul>
              </div>
            ))
          )}
        </div>

        <div className="sidebar__profile">
          <span className="sidebar__profile-avatar" aria-hidden="true">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none">
              <path
                d="M20 21v-2a4 4 0 00-4-4H8a4 4 0 00-4 4v2"
                stroke="currentColor"
                strokeWidth="2"
                strokeLinecap="round"
                strokeLinejoin="round"
              />
              <circle
                cx="12"
                cy="7"
                r="4"
                stroke="currentColor"
                strokeWidth="2"
              />
            </svg>
          </span>
          <span className="sidebar__profile-name">Marlabs PM</span>
        </div>
      </aside>
    </>
  );
}
