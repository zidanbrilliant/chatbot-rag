import React, { useState } from 'react'
import { login, setSession } from '../api'

export default function Login() {
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState(null)
  const [busy, setBusy] = useState(false)

  async function handleSubmit(e) {
    e.preventDefault()
    setError(null)
    setBusy(true)
    try {
      const data = await login(username, password)
      setSession(data.token, { username: data.username, role: data.role })
      window.location.reload()
    } catch (err) {
      setError(err.response?.data?.detail || 'Login gagal')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="login-container">
      <form onSubmit={handleSubmit} className="login-form">
        <h2>Knowledge Base Chatbot</h2>
        <p className="login-subtitle">Silakan login untuk melanjutkan</p>
        <label>
          Username
          <input
            type="text"
            value={username}
            onChange={(e) => setUsername(e.target.value)}
            required
            autoFocus
          />
        </label>
        <label>
          Password
          <input
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            required
          />
        </label>
        {error && <div className="login-error">{error}</div>}
        <button type="submit" disabled={busy}>
          {busy ? 'Logging in...' : 'Login'}
        </button>
      </form>
    </div>
  )
}
