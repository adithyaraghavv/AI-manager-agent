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

  // `autoTitle` is derived fresh from the first user message on every save. Once a PM
  // renames a conversation by hand, titleIsCustom keeps that name from being silently
  // overwritten by the next auto-save.
  const saveEntry = useCallback((id, autoTitle, messages) => {
    setEntries((prev) => {
      const existing = prev.find((e) => e.id === id)
      const title = existing?.titleIsCustom ? existing.title : autoTitle
      const updated = [
        { id, title, titleIsCustom: existing?.titleIsCustom ?? false, messages, updatedAt: new Date().toISOString() },
        ...prev.filter((e) => e.id !== id),
      ]
      persist(updated)
      return updated.slice(0, MAX_ENTRIES)
    })
  }, [])

  const renameEntry = useCallback((id, title) => {
    const trimmed = title.trim()
    if (!trimmed) return
    setEntries((prev) => {
      const updated = prev.map((e) => (e.id === id ? { ...e, title: trimmed, titleIsCustom: true } : e))
      persist(updated)
      return updated
    })
  }, [])

  const deleteEntry = useCallback((id) => {
    setEntries((prev) => {
      const updated = prev.filter((e) => e.id !== id)
      persist(updated)
      return updated
    })
  }, [])

  return { entries, saveEntry, renameEntry, deleteEntry }
}
