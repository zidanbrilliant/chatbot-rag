import React, { useState } from 'react'
import Chat from './components/Chat'
import AdminPanel from './components/AdminPanel'
import './App.css'

export default function App() {
  const [tab, setTab] = useState('chat')

  return (
    <div className="app">
      <header className="app-header">
        <h1>Knowledge Base Chatbot</h1>
        <nav>
          <button onClick={() => setTab('chat')} className={tab === 'chat' ? 'active' : ''}>
            Chat
          </button>
          <button onClick={() => setTab('admin')} className={tab === 'admin' ? 'active' : ''}>
            Admin Panel
          </button>
        </nav>
      </header>
      <main>
        {tab === 'chat' ? <Chat /> : <AdminPanel />}
      </main>
    </div>
  )
}
