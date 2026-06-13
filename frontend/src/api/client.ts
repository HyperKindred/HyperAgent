import axios from 'axios'

const api = axios.create({
  baseURL: '/api',
  timeout: 120000,
  headers: { 'Content-Type': 'application/json' },
})

/** Send a chat message and get the agent's reply. */
export async function sendChat(message: string): Promise<string> {
  const { data } = await api.post('/chat', { message })
  return data.reply
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
