import axios from 'axios'

const api = axios.create({
  baseURL: '/api/v1',
})

export function sendQuery(sessionId, query) {
  return api.post('/chat/query', { session_id: sessionId, query })
}

export function uploadDocument(file) {
  const form = new FormData()
  form.append('file', file)
  return api.post('/documents/upload', form, {
    headers: { 
      'Content-Type': 'multipart/form-data',
      'X-API-Key': 'supersecret'
    },
  })
}

export function listDocuments(page = 1, perPage = 50) {
  return api.get(`/documents?page=${page}&per_page=${perPage}`, {
    headers: { 'X-API-Key': 'supersecret' }
  })
}

export function deleteDocument(id) {
  return api.delete(`/documents/${id}`, {
    headers: { 'X-API-Key': 'supersecret' }
  })
}
