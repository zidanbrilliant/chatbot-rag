import React, { useEffect, useState } from 'react'
import Chat from './components/Chat'
import AdminPanel from './components/AdminPanel'
import Login from './components/Login'
import { clearSession, getToken, getUser, login, setSession } from './api'
import './App.css'

export default function App() {
  const [token, setToken] = useState(getToken())
  const [user, setUser] = useState(getUser())
  const [tab, setTab] = useState('chat')

  useEffect(() => {
    setToken(getToken())
    setUser(getUser())
  }, [])

  if (!token) {
    return <Login />
  }

  function handleLogout() {
    clearSession()
    setToken(null)
    setUser(null)
  }

  const canAdmin = user && ['document_admin', 'system_admin'].includes(user.role)
  const canAudit = user && ['system_admin', 'auditor'].includes(user.role)

  return (
    <div className="app">
      <header className="app-header">
        <h1>Knowledge Base Chatbot</h1>
        <nav>
          <button onClick={() => setTab('chat')} className={tab === 'chat' ? 'active' : ''}>
            Chat
          </button>
          {canAdmin && (
            <button onClick={() => setTab('admin')} className={tab === 'admin' ? 'active' : ''}>
              Admin Panel
            </button>
          )}
        </nav>
        <div className="user-info">
          <span>{user?.username} ({user?.role})</span>
          <button onClick={handleLogout} className="logout-btn">Logout</button>
        </div>
      </header>
      <main>
        {tab === 'chat' ? <Chat user={user} /> : (canAdmin ? <AdminPanel /> : <Chat user={user} />)}
      </main>
    </div>
  )
}
