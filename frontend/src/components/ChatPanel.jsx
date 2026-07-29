import { useEffect, useRef, useState } from 'react'
import { sendChat } from '../api'
import ToolActivity from './ToolActivity'

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

export default function ChatPanel() {
  const [messages, setMessages] = useState([])
  const [input, setInput] = useState('')
  const [sending, setSending] = useState(false)
  const [error, setError] = useState(null)
  const scrollRef = useRef(null)

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: 'smooth' })
  }, [messages])

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

  return (
    <div className="chat-panel">
      <div className="chat-panel__messages" ref={scrollRef}>
        {messages.length === 0 && (
          <div className="chat-panel__empty">
            Ask for a template, e.g. "I'm starting a new project with Hillenbrand, can I get the pricing template?"
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
      </div>

      {error && <div className="chat-panel__error">{error}</div>}

      <div className="chat-panel__input">
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
