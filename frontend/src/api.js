import axios from 'axios'

const api = axios.create({
  baseURL: '/api/v1',
})

export function sendQuery(sessionId, query) {
  return api.post('/chat/query', { session_id: sessionId, query })
}

export function sendQueryStream(sessionId, query, onToken, onDone, onError) {
  const controller = new AbortController()

  fetch('/api/v1/chat/stream', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ session_id: sessionId, query }),
    signal: controller.signal,
  }).then(async (response) => {
    const reader = response.body.getReader()
    const decoder = new TextDecoder()
    let buffer = ''

    while (true) {
      const { done, value } = await reader.read()
      if (done) break

      buffer += decoder.decode(value, { stream: true })
      const lines = buffer.split('\n')
      buffer = lines.pop() || ''

      for (const line of lines) {
        if (!line.startsWith('data: ')) continue
        try {
          const event = JSON.parse(line.slice(6))
          if (event.event === 'token') {
            onToken(event.text)
          } else if (event.event === 'done') {
            onDone(event)
          } else if (event.event === 'fallback') {
            onDone(event)
          } else if (event.event === 'error') {
            onError(event.text)
          }
        } catch {
          // skip malformed events
        }
      }
    }
  }).catch((err) => {
    if (err.name !== 'AbortError') {
      onError('Gagal terhubung ke server.')
    }
  })

  return controller
}

export function sendFallback(sessionId, query) {
  return api.post('/chat/fallback', { session_id: sessionId, query })
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

export function listDocuments() {
  return api.get('/documents', {
    headers: { 'X-API-Key': 'supersecret' }
  })
}

export function deleteDocument(id) {
  return api.delete(`/documents/${id}`, {
    headers: { 'X-API-Key': 'supersecret' }
  })
}
