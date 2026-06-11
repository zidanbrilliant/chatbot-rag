import React, { useState, useRef, useEffect } from "react";
import { sendQuery } from "../api";
import PriceCitations from "./PriceCitations";

export default function Chat() {
  const [sessionId, setSessionId] = useState(null);
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const bottomRef = useRef(null);
  const inputRef = useRef(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  function focusInput() {
    setTimeout(() => inputRef.current?.focus(), 50);
  }

  async function handleSend(e) {
    e?.preventDefault();
    const q = input.trim();
    if (!q || loading) return;

    setInput("");
    setLoading(true);
    setError(null);
    setMessages((prev) => [...prev, { role: "user", content: q }]);
    setMessages((prev) => [
      ...prev,
      { role: "assistant", content: "", _streaming: true, sources: [] },
    ]);

    try {
      const res = await sendQuery(sessionId, q);
      const data = res.data;
      if (data.session_id) setSessionId(data.session_id);
      setMessages((prev) => {
        const updated = [...prev];
        for (let i = updated.length - 1; i >= 0; i--) {
          if (updated[i].role === "assistant" && updated[i]._streaming) {
            updated[i] = {
              ...updated[i],
              content: data.reply || "",
              _streaming: false,
              sources: data.sources || [],
              metadata: data.metadata || {},
            };
            return updated;
          }
        }
        updated.push({
          role: "assistant",
          content: data.reply || "",
          sources: data.sources || [],
          metadata: data.metadata || {},
        });
        return updated;
      });
    } catch {
      setError("Gagal terhubung ke server. Silakan coba lagi.");
      setMessages((prev) => {
        const updated = [...prev];
        for (let i = updated.length - 1; i >= 0; i--) {
          if (updated[i].role === "assistant" && updated[i]._streaming) {
            updated[i] = { ...updated[i], _streaming: false, content: "" };
            return updated;
          }
        }
        return prev;
      });
    }
    setLoading(false);
    setInput("");
    focusInput();
  }

  function newChat() {
    setSessionId(null);
    setMessages([]);
    setError(null);
    focusInput();
  }

  function handleKeyDown(e) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  }

  return (
    <div className="chat-container">
      <div className="chat-header">
        <h2>Chat</h2>
        <div className="chat-actions">
          <button onClick={newChat} className="new-chat-btn">Chat Baru</button>
        </div>
      </div>

      <div className="messages">
        {messages.length === 0 && !loading && (
          <div className="welcome-card">
            <div className="welcome-icon">🤖</div>
            <h3>Halo! 👋</h3>
            <p>Aku asisten AI untuk mencari informasi dari dokumen dan sumber online.</p>
            <p className="welcome-hint">Tanyakan apa saja — aku akan cari dari knowledge base dan web.</p>
          </div>
        )}

        {messages.map((m, i) => (
          <div key={i} className={`message ${m.role}`}>
            <div className="bubble">
              {m.content}
              {m._streaming && m.content.length === 0 && (
                <span className="typing-dots">
                  <span className="typing-dot" />
                  <span className="typing-dot" />
                  <span className="typing-dot" />
                </span>
              )}
              {m.metadata?.nl_sources && m.metadata.nl_sources.length > 0 && !m._streaming && (
                <PriceCitations
                  sources={m.metadata.nl_sources}
                  intent={m.metadata.intent}
                />
              )}
              {m.sources && m.sources.length > 0 && !m._streaming && !m.metadata?.nl_sources && (
                <div className="sources">
                  {m.sources.filter(s => s.source_type === "internal").length > 0 && (
                    <div className="source-group">
                      <span className="badge badge-internal">📁 Knowledge Base</span>
                      {m.sources.filter(s => s.source_type === "internal").map((s, j) => (
                        <span key={j} className="source-item">{s.file_name}</span>
                      ))}
                    </div>
                  )}
                  {m.sources.filter(s => s.source_type === "external").length > 0 && (
                    <div className="source-group">
                      <span className="badge badge-external">🌐 Web</span>
                      {m.sources.filter(s => s.source_type === "external").map((s, j) => (
                        <a key={j} href={s.url} target="_blank" rel="noreferrer" className="source-item source-link">
                          {s.title || s.url}
                        </a>
                      ))}
                    </div>
                  )}
                </div>
              )}
            </div>
          </div>
        ))}

        {error && (
          <div className="message assistant">
            <div className="bubble bubble-error">{error}</div>
          </div>
        )}

        <div ref={bottomRef} />
      </div>

      <form onSubmit={handleSend} className="input-form">
        <input
          ref={inputRef}
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder="Tanya apa saja... (Enter kirim, Shift+Enter baris baru)"
          autoFocus
        />
        <button type="submit" disabled={loading || !input.trim()}>
          {loading ? "..." : "Kirim"}
        </button>
      </form>
    </div>
  );
}
