import { useEffect, useRef, useState } from 'react'
import { deleteClient, sendChat, uploadDocument } from '../api'
import { useChatHistory } from '../hooks/useChatHistory'
import AttachUploadCard from './AttachUploadCard'
import ChatHistoryMenu from './ChatHistoryMenu'
import DeleteConfirmCard from './DeleteConfirmCard'
import DeleteResult from './DeleteResult'
import ToolActivity from './ToolActivity'
import UploadResult from './UploadResult'

function BubbleAvatar({ role, hidden }) {
  if (hidden) return <span className="bubble-avatar bubble-avatar--spacer" aria-hidden="true" />
  if (role === 'user') {
    return (
      <span className="bubble-avatar bubble-avatar--user" aria-hidden="true">
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none">
          <path
            d="M20 21v-2a4 4 0 00-4-4H8a4 4 0 00-4 4v2"
            stroke="currentColor"
            strokeWidth="2"
            strokeLinecap="round"
            strokeLinejoin="round"
          />
          <circle cx="12" cy="7" r="4" stroke="currentColor" strokeWidth="2" />
        </svg>
      </span>
    )
  }
  // Marlabs-branded mark for the assistant, not a generic robot icon —
  // brand-gradient circle with the wordmark's "M", same navy/blue as the
  // header logo.
  return (
    <span className="bubble-avatar bubble-avatar--assistant" aria-hidden="true">
      M
    </span>
  )
}

function CopyButton({ text }) {
  const [copied, setCopied] = useState(false)

  async function handleCopy() {
    try {
      await navigator.clipboard.writeText(text)
      setCopied(true)
      setTimeout(() => setCopied(false), 1500)
    } catch {
      // Clipboard permission denied or unavailable — nothing useful to do,
      // fail silently rather than show a scary error for a convenience action.
    }
  }

  return (
    <button type="button" className="bubble__copy" onClick={handleCopy} title="Copy message">
      {copied ? (
        <svg width="13" height="13" viewBox="0 0 24 24" fill="none" aria-hidden="true">
          <path d="M5 13l4 4L19 7" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
        </svg>
      ) : (
        <svg width="13" height="13" viewBox="0 0 24 24" fill="none" aria-hidden="true">
          <rect x="9" y="9" width="12" height="12" rx="2" stroke="currentColor" strokeWidth="1.6" />
          <path d="M5 15V5a2 2 0 012-2h10" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
        </svg>
      )}
      <span className="sr-only">{copied ? 'Copied' : 'Copy message'}</span>
    </button>
  )
}

function extractText(content) {
  if (typeof content === 'string') return content
  if (Array.isArray(content)) {
    return content
      .filter((block) => block.type === 'text')
      .map((block) => block.text)
      .join('\n')
  }
  return ''
}

// Scans backwards through the conversation for the most recent client_name /
// doc_type the PM mentioned (read from the arguments of past tool calls, not
// their results — the result JSON doesn't echo back what was asked for).
// Purely a UX convenience — the user still confirms/edits before anything
// uploads, so a wrong guess here can't cause a wrong upload.
function inferUploadContext(messages) {
  let clientName = ''
  let docType = ''

  for (let i = messages.length - 1; i >= 0; i--) {
    const msg = messages[i]
    if (msg.role !== 'assistant' || !msg.tool_calls) continue

    for (const call of msg.tool_calls) {
      let args
      try {
        args = JSON.parse(call.function.arguments)
      } catch {
        continue
      }
      if (!clientName && args.client_name) clientName = args.client_name
      if (!docType && call.function.name === 'request_template' && args.doc_type) docType = args.doc_type
    }

    if (clientName && docType) break
  }

  return { clientName, docType }
}

export default function ChatPanel() {
  const [messages, setMessages] = useState([])
  const [input, setInput] = useState('')
  const [sending, setSending] = useState(false)
  const [error, setError] = useState(null)
  const [pendingFile, setPendingFile] = useState(null)
  const [pendingDelete, setPendingDelete] = useState(null)
  const [dragActive, setDragActive] = useState(false)
  const [showHistory, setShowHistory] = useState(false)
  const [chatId, setChatId] = useState(null)
  const scrollRef = useRef(null)
  const fileInputRef = useRef(null)
  const textareaRef = useRef(null)
  const dragDepth = useRef(0)
  const chatIdRef = useRef(null)
  const { entries: chatHistory, saveEntry, deleteEntry } = useChatHistory()

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: 'smooth' })
  }, [messages, pendingFile])

  // Auto-grow the composer only as far as the content actually needs —
  // starts at one line, expands with typed content, and collapses back
  // down (not left tall) once the message is sent or cleared.
  useEffect(() => {
    const el = textareaRef.current
    if (!el) return
    el.style.height = 'auto'
    el.style.height = `${el.scrollHeight}px`
  }, [input])

  // Auto-save to the local chat history sidebar after every exchange that has
  // real user content — a fresh chatId is minted on the first user message, so
  // reloads/edits to the same conversation update one entry instead of piling
  // up duplicates.
  useEffect(() => {
    const userMessages = messages.filter((m) => m.role === 'user')
    if (userMessages.length === 0) return

    if (!chatIdRef.current) {
      chatIdRef.current = Date.now()
      setChatId(chatIdRef.current)
    }
    const title = extractText(userMessages[0].content).slice(0, 60) || 'New chat'
    saveEntry(chatIdRef.current, title, messages)
  }, [messages, saveEntry])

  // Shared by both a fresh send and a retry — `outgoing` already contains
  // the user's message (appended by the caller), so this never duplicates
  // it. Keeping this separate from handleSend is what lets retry resend the
  // same request without adding a second copy of the failed message.
  async function sendToBackend(outgoing) {
    setSending(true)
    setError(null)

    try {
      const response = await sendChat(outgoing)
      const newlyAdded = response.messages.slice(outgoing.length)
      setMessages((prev) => [...prev, ...newlyAdded])

      // The agent never deletes anything itself — propose_delete_client only looks a client
      // up. If it did, surface a confirm/cancel card; the actual delete only happens if the
      // PM clicks confirm, which hits DELETE /api/clients/{name} directly.
      for (const msg of newlyAdded) {
        if (msg.role !== 'tool' || msg.name !== 'propose_delete_client') continue
        try {
          const result = JSON.parse(msg.content)
          if (result.found && result.needs_confirmation) setPendingDelete(result)
        } catch {
          // ignore malformed tool content — nothing to confirm
        }
      }
    } catch (err) {
      // Show a human fallback in the UI; keep the real error only in the
      // console, for debugging — a raw "Chat request failed (500): ..." string
      // reads as broken, not helpful, to someone using this live.
      console.error('Chat request failed:', err)
      setError('Something went wrong reaching the assistant — check your connection and try again.')
    } finally {
      setSending(false)
    }
  }

  async function handleSend(textOverride) {
    const text = (textOverride ?? input).trim()
    if (!text || sending) return

    const userMsg = { role: 'user', content: text }
    const updated = [...messages, userMsg]
    setMessages(updated)
    setInput('')

    // upload-result/delete-result entries are local-only display items — OpenAI rejects any
    // role it doesn't recognize, so they must never be sent to the backend.
    const outgoing = updated.filter((m) => m.role !== 'upload-result' && m.role !== 'delete-result')
    await sendToBackend(outgoing)
  }

  function handleRetry() {
    const outgoing = messages.filter((m) => m.role !== 'upload-result' && m.role !== 'delete-result')
    sendToBackend(outgoing)
  }

  function handleNewChat() {
    chatIdRef.current = null
    setChatId(null)
    setMessages([])
    setInput('')
    setError(null)
    setPendingFile(null)
    setPendingDelete(null)
  }

  function handleLoadChat(entry) {
    if (chatIdRef.current === entry.id) return
    chatIdRef.current = entry.id
    setChatId(entry.id)
    setMessages(entry.messages)
    setInput('')
    setError(null)
    setPendingFile(null)
    setPendingDelete(null)
  }

  function handleDeleteChat(id) {
    deleteEntry(id)
    if (chatIdRef.current === id) handleNewChat()
  }

  function handleKeyDown(e) {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSend()
    }
  }

  function handleFilePicked(e) {
    const file = e.target.files[0]
    if (file) setPendingFile(file)
    e.target.value = '' // allow re-picking the same file later
  }

  // Enter/leave counter avoids flicker from drag events firing on child
  // elements as the pointer moves over them — only the outermost enter/leave
  // (depth 0) should toggle the overlay.
  function handleDragEnter(e) {
    e.preventDefault()
    dragDepth.current += 1
    if (e.dataTransfer.types.includes('Files')) setDragActive(true)
  }

  function handleDragOver(e) {
    e.preventDefault()
  }

  function handleDragLeave(e) {
    e.preventDefault()
    dragDepth.current -= 1
    if (dragDepth.current <= 0) {
      dragDepth.current = 0
      setDragActive(false)
    }
  }

  function handleDrop(e) {
    e.preventDefault()
    dragDepth.current = 0
    setDragActive(false)
    const file = e.dataTransfer.files[0]
    if (file) setPendingFile(file)
  }

  async function handleUploadConfirm(clientName, docType) {
    try {
      const result = await uploadDocument(clientName, docType, pendingFile)
      setMessages((prev) => [
        ...prev,
        { role: 'upload-result', content: { ok: true, result: { ...result, client_name: clientName } } },
      ])
    } catch (err) {
      setMessages((prev) => [...prev, { role: 'upload-result', content: { ok: false, error: err.message } }])
    } finally {
      setPendingFile(null)
    }
  }

  async function handleDeleteConfirm(clientName) {
    try {
      await deleteClient(clientName)
      setMessages((prev) => [...prev, { role: 'delete-result', content: { ok: true, clientName } }])
    } catch (err) {
      setMessages((prev) => [...prev, { role: 'delete-result', content: { ok: false, error: err.message } }])
    } finally {
      setPendingDelete(null)
    }
  }

  function handleDeleteCancel() {
    setMessages((prev) => [...prev, { role: 'delete-result', content: { cancelled: true, clientName: pendingDelete.client_name } }])
    setPendingDelete(null)
  }

  const uploadContext = pendingFile ? inferUploadContext(messages) : null
  const hasConversation = messages.length > 0 || pendingFile || pendingDelete

  return (
    <div
      className="chat-panel"
      onDragEnter={handleDragEnter}
      onDragOver={handleDragOver}
      onDragLeave={handleDragLeave}
      onDrop={handleDrop}
    >
      {dragActive && (
        <div className="chat-panel__drop-overlay">
          <div className="chat-panel__drop-overlay-inner">
            <svg width="32" height="32" viewBox="0 0 24 24" fill="none" aria-hidden="true">
              <path
                d="M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4M17 8l-5-5-5 5M12 3v12"
                stroke="currentColor"
                strokeWidth="1.8"
                strokeLinecap="round"
                strokeLinejoin="round"
              />
            </svg>
            <span>Drop to attach</span>
          </div>
        </div>
      )}
      {(hasConversation || chatHistory.length > 0) && (
        <div className="chat-panel__topbar">
          <div className="chat-panel__history-wrap">
            <button
              type="button"
              className="chat-panel__history-toggle"
              onClick={() => setShowHistory((s) => !s)}
              disabled={chatHistory.length === 0}
            >
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" aria-hidden="true">
                <path
                  d="M3 12a9 9 0 109-9M3 12l3-3M3 12l3 3M12 7v5l3 3"
                  stroke="currentColor"
                  strokeWidth="1.8"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                />
              </svg>
              History
            </button>
            {showHistory && (
              <ChatHistoryMenu
                entries={chatHistory}
                activeId={chatId}
                onLoad={handleLoadChat}
                onDelete={handleDeleteChat}
                onClose={() => setShowHistory(false)}
              />
            )}
          </div>
          {hasConversation && (
            <button type="button" className="chat-panel__new-chat" onClick={handleNewChat}>
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" aria-hidden="true">
                <path d="M12 5v14M5 12h14" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
              </svg>
              New chat
            </button>
          )}
        </div>
      )}
      <div className="chat-panel__messages" ref={scrollRef}>
       <div className="chat-panel__messages-inner">
        {messages.length === 0 && !pendingFile && (
          <div className="bubble-row bubble-row--assistant">
            <BubbleAvatar role="assistant" />
            <div className="bubble bubble--assistant">
              <div className="bubble__text">
                Hey! What can I help with — checking on a client, grabbing a template, or filing
                something you've finished? You can also just drop a file in with the 📎 below if
                that's easier.
              </div>
            </div>
          </div>
        )}
        {(() => {
          let previousBubbleRole = null
          return messages.map((msg, i) => {
            if (msg.role === 'tool') {
              previousBubbleRole = null
              let result
              try {
                result = JSON.parse(msg.content)
              } catch {
                return null
              }
              return <ToolActivity key={i} name={msg.name} result={result} />
            }

            if (msg.role === 'upload-result') {
              previousBubbleRole = null
              return <UploadResult key={i} result={msg.content.result} error={msg.content.error} />
            }

            if (msg.role === 'delete-result') {
              previousBubbleRole = null
              return (
                <DeleteResult
                  key={i}
                  clientName={msg.content.clientName}
                  error={msg.content.error}
                  cancelled={msg.content.cancelled}
                />
              )
            }

            const text = extractText(msg.content)
            if (msg.role === 'assistant' && !text) return null

            // Consecutive messages from the same sender stack tightly with a
            // single avatar (shown once, on the first of the run) instead of
            // repeating "You"/"Agent" labels and an avatar on every bubble.
            const grouped = previousBubbleRole === msg.role
            previousBubbleRole = msg.role

            return (
              <div key={i} className={`bubble-row bubble-row--${msg.role}${grouped ? ' bubble-row--grouped' : ''}`}>
                <BubbleAvatar role={msg.role} hidden={grouped} />
                <div className={`bubble bubble--${msg.role}`}>
                  <div className="bubble__text-wrap">
                    <div className="bubble__text">{text}</div>
                    <CopyButton text={text} />
                  </div>
                </div>
              </div>
            )
          })
        })()}
        {sending && (
          <div className="bubble-row bubble-row--assistant">
            <BubbleAvatar role="assistant" />
            <div className="chat-panel__typing" aria-label="Agent is thinking">
              <span className="chat-panel__typing-dot" />
              <span className="chat-panel__typing-dot" />
              <span className="chat-panel__typing-dot" />
            </div>
          </div>
        )}
        {pendingFile && (
          <AttachUploadCard
            file={pendingFile}
            initialClientName={uploadContext?.clientName}
            initialDocType={uploadContext?.docType}
            onConfirm={handleUploadConfirm}
            onCancel={() => setPendingFile(null)}
          />
        )}
        {pendingDelete && (
          <DeleteConfirmCard proposal={pendingDelete} onConfirm={handleDeleteConfirm} onCancel={handleDeleteCancel} />
        )}
       </div>
      </div>

      {error && (
        <div className="chat-panel__error">
          <span>{error}</span>
          <button type="button" className="chat-panel__retry" onClick={handleRetry}>
            Retry
          </button>
        </div>
      )}

      <div className="chat-panel__input">
        <textarea
          ref={textareaRef}
          className="chat-panel__textarea"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder="Ask the delivery assistant…"
          rows={1}
          disabled={sending}
        />
        <div className="chat-panel__toolbar">
          <button
            type="button"
            className="chat-panel__icon-btn"
            title="Attach a completed document"
            onClick={() => fileInputRef.current?.click()}
            disabled={sending}
          >
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" aria-hidden="true">
              <path
                d="M20.5 12.5L12.83 20.17a5 5 0 01-7.07-7.07L13.83 5a3.5 3.5 0 014.95 4.95l-7.78 7.78a2 2 0 01-2.83-2.83l7.07-7.07"
                stroke="currentColor"
                strokeWidth="1.8"
                strokeLinecap="round"
                strokeLinejoin="round"
              />
            </svg>
            <span className="sr-only">Attach a completed document</span>
          </button>
          <input ref={fileInputRef} type="file" hidden onChange={handleFilePicked} />
          <button
            type="button"
            className="chat-panel__send-btn"
            title="Send"
            onClick={() => handleSend()}
            disabled={sending || !input.trim()}
          >
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" aria-hidden="true">
              <path d="M12 19V5M12 5L6 11M12 5l6 6" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" />
            </svg>
            <span className="sr-only">Send</span>
          </button>
        </div>
      </div>
    </div>
  )
}
