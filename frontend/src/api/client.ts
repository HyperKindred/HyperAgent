import axios from 'axios'

const api = axios.create({
  baseURL: '/api',
  timeout: 120000,
  headers: { 'Content-Type': 'application/json' },
})

/** Send a chat message and get the agent's reply. */
export async function sendChat(
  message: string,
  threadId?: string,
): Promise<string> {
  const payload: Record<string, string> = { message }
  if (threadId) {
    payload.thread_id = threadId
  }
  const { data } = await api.post('/chat', payload)
  return data.reply
}

/** Create a new conversation thread and return its ID. */
export async function createThread(): Promise<string> {
  const { data } = await api.post('/threads')
  return data.thread_id
}

export interface EventItem {
  id: number
  title: string
  description: string
  start_time: string
  end_time: string | null
  status: string
  priority: string
  category: string
}

/** List events, optionally filtered by date. */
export async function fetchEvents(date?: string): Promise<EventItem[]> {
  const params: Record<string, string> = {}
  if (date) params.dt = date
  const { data } = await api.get('/events', { params })
  return data
}

/** Create an event directly (bypass LLM agent). */
export async function createEvent(payload: {
  title: string
  start_time: string
  end_time?: string
  description?: string
  priority?: string
}): Promise<EventItem> {
  const { data } = await api.post('/events', payload)
  return data
}

/** Delete an event by ID. */
export async function deleteEvent(id: number): Promise<void> {
  await api.delete(`/events/${id}`)
}

/**
 * Send a chat message and stream the response token by token.
 * Uses native fetch() + ReadableStream to consume SSE events from /api/chat/stream.
 */
export async function* sendChatStream(
  message: string,
  threadId?: string,
): AsyncGenerator<string> {
  const payload: Record<string, string> = { message }
  if (threadId) payload.thread_id = threadId

  const response = await fetch('/api/chat/stream', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })

  if (!response.ok) throw new Error(`HTTP ${response.status}`)

  const reader = response.body!.getReader()
  const decoder = new TextDecoder()
  let buffer = ''

  while (true) {
    const { done, value } = await reader.read()
    if (done) break

    buffer += decoder.decode(value, { stream: true })
    const lines = buffer.split('\n')
    buffer = lines.pop() || ''

    for (const line of lines) {
      if (line.startsWith('data: ')) {
        const data = JSON.parse(line.slice(6))
        if (data.type === 'token') yield data.content
        if (data.type === 'done') return
        if (data.type === 'error') throw new Error(data.content)
      }
    }
  }
}

