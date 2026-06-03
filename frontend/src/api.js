import axios from 'axios'

const api = axios.create({
  baseURL: '/api/v1',
})

export function sendQuery(sessionId, query) {
  return api.post('/chat/query', { session_id: sessionId, query })
}

export function sendFallback(sessionId, query) {
  return api.post('/chat/fallback', { session_id: sessionId, query })
}

export function uploadDocument(file) {
  const form = new FormData()
  form.append('file', file)
  return api.post('/documents/upload', form, {
    headers: { 'Content-Type': 'multipart/form-data' },
  })
}

export function listDocuments() {
  return api.get('/documents')
}

export function deleteDocument(id) {
  return api.delete(`/documents/${id}`)
}
