import { useCallback, useState } from 'react'

const STORAGE_KEY = 'delivery_assistant_chat_history'
const MAX_ENTRIES = 30

function load() {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    return raw ? JSON.parse(raw) : []
  } catch {
    return []
  }
}

function persist(entries) {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(entries.slice(0, MAX_ENTRIES)))
  } catch {
    // localStorage unavailable (private browsing, quota) — history just won't persist
  }
}

// Saved conversations are a local-only convenience — nothing here is sent to or read
// from the backend, so a wiped browser/localStorage just means lost history, never a
// data-integrity issue for anything that actually matters (client documents, gating).
export function useChatHistory() {
  const [entries, setEntries] = useState(load)

  const saveEntry = useCallback((id, title, messages) => {
    setEntries((prev) => {
      const updated = [{ id, title, messages, updatedAt: new Date().toISOString() }, ...prev.filter((e) => e.id !== id)]
      persist(updated)
      return updated.slice(0, MAX_ENTRIES)
    })
  }, [])

  const deleteEntry = useCallback((id) => {
    setEntries((prev) => {
      const updated = prev.filter((e) => e.id !== id)
      persist(updated)
      return updated
    })
  }, [])

  return { entries, saveEntry, deleteEntry }
}
