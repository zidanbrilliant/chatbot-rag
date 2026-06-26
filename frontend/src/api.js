import axios from 'axios'

const api = axios.create({ baseURL: '/api/v1' })

const TOKEN_KEY = 'kb_token'
const USER_KEY = 'kb_user'

export function getToken() {
  return localStorage.getItem(TOKEN_KEY)
}

export function getUser() {
  const raw = localStorage.getItem(USER_KEY)
  return raw ? JSON.parse(raw) : null
}

export function setSession(token, user) {
  localStorage.setItem(TOKEN_KEY, token)
  localStorage.setItem(USER_KEY, JSON.stringify(user))
}

export function clearSession() {
  localStorage.removeItem(TOKEN_KEY)
  localStorage.removeItem(USER_KEY)
}

api.interceptors.request.use((config) => {
  const token = getToken()
  if (token) {
    config.headers.Authorization = `Bearer ${token}`
  }
  return config
})

api.interceptors.response.use(
  (resp) => resp,
  (err) => {
    if (err.response && err.response.status === 401) {
      clearSession()
      window.location.reload()
    }
    return Promise.reject(err)
  },
)

export function login(username, password) {
  return api.post('/auth/login', { username, password }).then((r) => r.data)
}

export function register(username, password, role) {
  return api.post('/auth/register', { username, password, role }).then((r) => r.data)
}

export function sendQuery(sessionId, query) {
  return api.post('/chat/query', { session_id: sessionId, query })
}

export function sendFeedback(sessionId, messageId, feedback) {
  return api.post('/chat/feedback', { session_id: sessionId, message_id: messageId, feedback })
}

export function uploadDocument(file) {
  const form = new FormData()
  form.append('file', file)
  return api.post('/documents/upload', form, {
    headers: { 'Content-Type': 'multipart/form-data' },
  })
}

export function listDocuments(page = 1, perPage = 50) {
  return api.get(`/documents?page=${page}&per_page=${perPage}`)
}

export function deleteDocument(id) {
  return api.delete(`/documents/${id}`)
}
