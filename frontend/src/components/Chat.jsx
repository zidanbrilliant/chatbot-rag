import React, { useState, useRef, useEffect } from "react";
import { sendQuery, sendFallback } from "../api";

export default function Chat() {
  const [sessionId, setSessionId] = useState(null);
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [pendingFallback, setPendingFallback] = useState(null);
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
    // placeholder untuk loading indicator
    setMessages((prev) => [
      ...prev,
      { role: "assistant", content: "", _streaming: true, sources: [] },
    ]);

    try {
      const res = await sendQuery(sessionId, q);
      const data = res.data;
      if (data.session_id) setSessionId(data.session_id);
      if (data.fallback_triggered) {
        setPendingFallback({ sessionId: data.session_id, query: q });
      }
      // replace placeholder with final response
      setMessages((prev) => {
        const updated = [...prev];
        for (let i = updated.length - 1; i >= 0; i--) {
          if (updated[i].role === "assistant" && updated[i]._streaming) {
            updated[i] = {
              ...updated[i],
              content: data.reply || "",
              _streaming: false,
              sources: data.sources || [],
            };
            return updated;
          }
        }
        updated.push({ role: "assistant", content: data.reply || "", sources: data.sources || [] });
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

  async function handleFallback(confirm) {
    if (!pendingFallback) return;
    if (!confirm) {
      setPendingFallback(null);
      focusInput();
      return;
    }
    setLoading(true);
    setPendingFallback(null);
    try {
      const res = await sendFallback(pendingFallback.sessionId, pendingFallback.query);
      const data = res.data;
      setMessages((prev) => [
        ...prev,
        { role: "assistant", content: data.reply, external_sources: data.external_sources, external: true },
      ]);
    } catch {
      setMessages((prev) => [
        ...prev,
        { role: "assistant", content: "Pencarian Google gagal.", external: true },
      ]);
    }
    setLoading(false);
    focusInput();
  }

  function newChat() {
    setSessionId(null);
    setMessages([]);
    setPendingFallback(null);
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
            <p>Aku asisten AI untuk mencari informasi dari dokumen yang sudah di-upload.</p>
            <p className="welcome-hint">Tanyakan apa saja seputar isi dokumen yang tersedia.</p>
          </div>
        )}

        {messages.map((m, i) => (
          <div key={i} className={`message ${m.role}`}>
            <div className={`bubble ${m.external ? "bubble-external" : ""}`}>
              {m.content}
              {m._streaming && m.content.length === 0 && (
                <span className="typing-dots">
                  <span className="typing-dot" />
                  <span className="typing-dot" />
                  <span className="typing-dot" />
                </span>
              )}
              {m.sources && m.sources.length > 0 && !m._streaming && (
                <div className="sources">
                  <small>Sumber: {m.sources.map((s) => s.file_name).join(", ")}</small>
                </div>
              )}
              {m.external_sources && m.external_sources.length > 0 && (
                <div className="sources">
                  <span className="badge">Sumber Eksternal</span>
                  {m.external_sources.map((s, j) => (
                    <div key={j}>
                      <a href={s.url} target="_blank" rel="noreferrer">{s.title}</a>
                    </div>
                  ))}
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

        {pendingFallback && (
          <div className="fallback-prompt">
            <p>Informasi tidak ditemukan di knowledge base.<br />Cari dari Google?</p>
            <button onClick={() => handleFallback(true)} className="btn-yes">Ya, cari di Google</button>
            <button onClick={() => handleFallback(false)} className="btn-no">Tidak</button>
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
