import React, { useState, useEffect } from 'react'
import { uploadDocument, listDocuments, deleteDocument } from '../api'

export default function AdminPanel() {
  const [docs, setDocs] = useState([])
  const [uploading, setUploading] = useState(false)
  const [message, setMessage] = useState('')

  useEffect(() => { loadDocs() }, [])

  async function loadDocs() {
    try {
      const res = await listDocuments()
      setDocs(res.data.data || [])
    } catch { setMessage('Failed to load documents') }
  }

  async function handleUpload(e) {
    const file = e.target.files[0]
    if (!file) return
    setUploading(true)
    setMessage('')
    try {
      await uploadDocument(file)
      setMessage('Upload successful. Processing...')
      loadDocs()
    } catch (err) {
      setMessage(err.response?.data?.detail || 'Upload failed')
    }
    setUploading(false)
    e.target.value = ''
  }

  async function handleDelete(id) {
    try {
      await deleteDocument(id)
      setMessage('Document deleted')
      loadDocs()
    } catch { setMessage('Delete failed') }
  }

  const statusColor = (s) => {
    if (s === 'INDEXED') return '#4caf50'
    if (s === 'PROCESSING') return '#ff9800'
    return '#f44336'
  }

  return (
    <div className="admin-panel">
      <h2>Document Management</h2>
      {message && <p className="status-message">{message}</p>}
      <div className="upload-area">
        <label className="upload-btn">
          {uploading ? 'Uploading...' : 'Upload Document'}
          <input type="file" onChange={handleUpload} accept=".pdf,.docx,.csv,.xlsx" hidden disabled={uploading} />
        </label>
        <small>PDF, DOCX, CSV, XLSX — max 50 MB</small>
      </div>
      <table>
        <thead>
          <tr><th>File Name</th><th>Size</th><th>Status</th><th>Uploaded</th><th>Action</th></tr>
        </thead>
        <tbody>
          {docs.map(d => (
            <tr key={d.id}>
              <td>{d.file_name}</td>
              <td>{(d.file_size / 1024).toFixed(1)} KB</td>
              <td><span className="status" style={{ background: statusColor(d.status) }}>{d.status}</span></td>
              <td>{new Date(d.created_at).toLocaleDateString()}</td>
              <td><button onClick={() => handleDelete(d.id)} className="delete-btn">Delete</button></td>
            </tr>
          ))}
        </tbody>
      </table>
      {docs.length === 0 && <p className="empty">No documents uploaded yet.</p>}
    </div>
  )
}
