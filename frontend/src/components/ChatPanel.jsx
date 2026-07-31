import { useEffect, useRef, useState } from 'react'
import { sendChat, uploadDocument } from '../api'
import AttachUploadCard from './AttachUploadCard'
import ToolActivity from './ToolActivity'
import UploadResult from './UploadResult'

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
  const scrollRef = useRef(null)
  const fileInputRef = useRef(null)

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: 'smooth' })
  }, [messages, pendingFile])

  async function handleSend() {
    const text = input.trim()
    if (!text || sending) return

    const nextMessages = [...messages, { role: 'user', content: text }]
    setMessages(nextMessages)
    setInput('')
    setSending(true)
    setError(null)

    try {
      const response = await sendChat(nextMessages)
      setMessages(response.messages)
    } catch (err) {
      setError(err.message)
    } finally {
      setSending(false)
    }
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

  const uploadContext = pendingFile ? inferUploadContext(messages) : null

  return (
    <div className="chat-panel">
      <div className="chat-panel__messages" ref={scrollRef}>
        {messages.length === 0 && !pendingFile && (
          <div className="chat-panel__empty">
            Ask for a template, e.g. "I'm starting a new project with Hillenbrand, can I get the pricing template?"
            <br />
            Or attach a completed document directly with the 📎 button below.
          </div>
        )}
        {messages.map((msg, i) => {
          if (msg.role === 'tool') {
            let result
            try {
              result = JSON.parse(msg.content)
            } catch {
              return null
            }
            return <ToolActivity key={i} name={msg.name} result={result} />
          }

          if (msg.role === 'upload-result') {
            return <UploadResult key={i} result={msg.content.result} error={msg.content.error} />
          }

          const text = extractText(msg.content)
          if (msg.role === 'assistant' && !text) return null

          return (
            <div key={i} className={`bubble bubble--${msg.role}`}>
              <div className="bubble__label">{msg.role === 'user' ? 'You' : 'Agent'}</div>
              <div className="bubble__text">{text}</div>
            </div>
          )
        })}
        {sending && <div className="chat-panel__typing">Agent is thinking…</div>}
        {pendingFile && (
          <AttachUploadCard
            file={pendingFile}
            initialClientName={uploadContext?.clientName}
            initialDocType={uploadContext?.docType}
            onConfirm={handleUploadConfirm}
            onCancel={() => setPendingFile(null)}
          />
        )}
      </div>

      {error && <div className="chat-panel__error">{error}</div>}

      <div className="chat-panel__input">
        <button
          type="button"
          className="chat-panel__attach"
          title="Attach a completed document"
          onClick={() => fileInputRef.current?.click()}
          disabled={sending}
        >
          📎
        </button>
        <input ref={fileInputRef} type="file" hidden onChange={handleFilePicked} />
        <textarea
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder="Ask the delivery assistant…"
          rows={2}
          disabled={sending}
        />
        <button onClick={handleSend} disabled={sending || !input.trim()}>
          Send
        </button>
      </div>
    </div>
  )
}
