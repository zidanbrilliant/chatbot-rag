import React, { useState, useRef, useEffect } from 'react'
import { sendQuery, sendFallback } from '../api'

export default function Chat() {
  const [sessionId, setSessionId] = useState(null)
  const [messages, setMessages] = useState([])
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)
  const [pendingFallback, setPendingFallback] = useState(null)
  const bottomRef = useRef(null)

  useEffect(() => { bottomRef.current?.scrollIntoView({ behavior: 'smooth' }) }, [messages])

  async function handleSend(e) {
    e.preventDefault()
    if (!input.trim() || loading) return
    const q = input.trim()
    setInput('')
    setMessages(prev => [...prev, { role: 'user', content: q }])
    setLoading(true)

    try {
      const res = await sendQuery(sessionId, q)
      const data = res.data
      setSessionId(data.session_id)

      if (data.fallback_triggered) {
        setPendingFallback({ sessionId: data.session_id, query: q })
        setMessages(prev => [...prev, { role: 'assistant', content: data.reply, fallback: true }])
      } else {
        setMessages(prev => [...prev, { role: 'assistant', content: data.reply, sources: data.sources, out_of_context: data.out_of_context }])
      }
    } catch (err) {
      setMessages(prev => [...prev, { role: 'assistant', content: 'Error: unable to get response.' }])
    }
    setLoading(false)
  }

  async function handleFallback(confirm) {
    if (!pendingFallback) return
    if (!confirm) { setPendingFallback(null); return }
    setLoading(true)
    try {
      const res = await sendFallback(pendingFallback.sessionId, pendingFallback.query)
      const data = res.data
      setMessages(prev => [...prev, {
        role: 'assistant',
        content: data.reply,
        external_sources: data.external_sources,
        external: true,
      }])
    } catch {
      setMessages(prev => [...prev, { role: 'assistant', content: 'Google Search unavailable.' }])
    }
    setPendingFallback(null)
    setLoading(false)
  }

  function newChat() {
    setSessionId(null)
    setMessages([])
    setPendingFallback(null)
  }

  return (
    <div className="chat-container">
      <div className="chat-header">
        <h2>Chat</h2>
        <button onClick={newChat} className="new-chat-btn">New Chat</button>
      </div>
      <div className="messages">
        {messages.length === 0 && !loading && (
          <div className="welcome-card">
            <div className="welcome-icon">🤖</div>
            <h3>Halo! 👋</h3>
            <p>Aku asisten AI pribadi. Siap bantu kamu mencari informasi dari dokumen yang di-upload.</p>
            <p className="welcome-hint">Tanya aja apa pun seputar isi dokumen yang ada!</p>
          </div>
        )}
        {messages.map((m, i) => (
          <div key={i} className={`message ${m.role}`}>
            <div className="bubble">
              {m.content}
              {m.sources && m.sources.length > 0 && (
                <div className="sources">
                  <small>Sources: {m.sources.map(s => s.file_name).join(', ')}</small>
                </div>
              )}
              {m.external_sources && m.external_sources.length > 0 && (
                <div className="sources">
                  <span className="badge">Sumber Eksternal</span>
                  {m.external_sources.map((s, j) => (
                    <div key={j}><a href={s.url} target="_blank" rel="noreferrer">{s.title}</a></div>
                  ))}
                </div>
              )}
              {m.out_of_context && <div className="badge">Out of Context</div>}
            </div>
          </div>
        ))}
        {loading && (
          <div className="message assistant">
            <div className="bubble typing-bubble">
              <span className="typing-dot"></span>
              <span className="typing-dot"></span>
              <span className="typing-dot"></span>
            </div>
          </div>
        )}
        {pendingFallback && (
          <div className="fallback-prompt">
            <p>Cari informasi ini dari Google?</p>
            <button onClick={() => handleFallback(true)} className="btn-yes">Ya</button>
            <button onClick={() => handleFallback(false)} className="btn-no">Tidak</button>
          </div>
        )}
        <div ref={bottomRef} />
      </div>
      <form onSubmit={handleSend} className="input-form">
        <input value={input} onChange={e => setInput(e.target.value)} placeholder="Tanya apa saja..." disabled={loading} />
        <button type="submit" disabled={loading || !input.trim()}>Kirim</button>
      </form>
    </div>
  )
}
