import React, { useState, useEffect } from 'react'
import { uploadDocument, listDocuments, deleteDocument } from '../api'

export default function AdminPanel() {
  const [docs, setDocs] = useState([])
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)
  const [totalPages, setTotalPages] = useState(1)
  const [uploading, setUploading] = useState(false)
  const [message, setMessage] = useState('')
  const [filter, setFilter] = useState('')

  useEffect(() => { loadDocs() }, [page, filter])

  async function loadDocs() {
    try {
      const res = await listDocuments(page, 50)
      const data = res.data
      setDocs(data.data || [])
      setTotal(data.total)
      setTotalPages(data.total_pages)
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
      setPage(1)
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

  function formatSize(bytes) {
    if (!bytes && bytes !== 0) return '-'
    if (bytes < 1024) return bytes + ' B'
    if (bytes < 1048576) return (bytes / 1024).toFixed(1) + ' KB'
    return (bytes / 1048576).toFixed(1) + ' MB'
  }

  const statusColor = (s) => {
    if (s === 'completed') return '#4caf50'
    if (s === 'processing') return '#ff9800'
    if (s === 'failed') return '#9e0000'
    if (s === 'queued') return '#2196f3'
    return '#f44336'
  }

  const filteredDocs = filter
    ? docs.filter(d => d.status === filter)
    : docs

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

      <div className="filter-bar">
        <span>Total: {total}</span>
        <select onChange={(e) => { setFilter(e.target.value); setPage(1) }} value={filter}>
          <option value="">All Status</option>
          <option value="queued">Queued</option>
          <option value="processing">Processing</option>
          <option value="completed">Completed</option>
          <option value="failed">Failed</option>
        </select>
      </div>

      <table>
        <thead>
          <tr><th>File Name</th><th>Size</th><th>Status</th><th>Type</th><th>Uploaded</th><th>Action</th></tr>
        </thead>
        <tbody>
          {filteredDocs.map(d => {
            const attr = d.attributes || {}
            const isCatalog = attr.ingestion_type === 'csv_catalog'
            return (
              <tr key={d.id}>
                <td>{d.original_filename || '-'}</td>
                <td>{formatSize(d.size_bytes)}</td>
                <td><span className="status" style={{ background: statusColor(d.status) }}>{d.status}</span></td>
                <td>
                  {isCatalog
                    ? <span title={`${attr.products_count || 0} products imported directly to DB`}>📦 catalog ({attr.products_count || 0})</span>
                    : '🔍 vector'}
                </td>
                <td>{d.created_at ? new Date(d.created_at).toLocaleDateString() : '-'}</td>
                <td><button onClick={() => handleDelete(d.id)} className="delete-btn">Delete</button></td>
              </tr>
            )
          })}
        </tbody>
      </table>

      {totalPages > 1 && (
        <div className="pagination">
          <button disabled={page <= 1} onClick={() => setPage(p => Math.max(1, p - 1))}>Previous</button>
          <span>Page {page} of {totalPages}</span>
          <button disabled={page >= totalPages} onClick={() => setPage(p => p + 1)}>Next</button>
        </div>
      )}

      {docs.length === 0 && <p className="empty">No documents uploaded yet.</p>}
    </div>
  )
}
