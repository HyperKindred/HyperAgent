import axios from 'axios'

const api = axios.create({
  baseURL: '/api',
  timeout: 120000,
  headers: { 'Content-Type': 'application/json' },
})

export interface ReindexStatus {
  state: 'idle' | 'running' | 'completed' | 'failed'
  total: number
  indexed: number
  failed: number
  fingerprint: string | null
}

export interface RuntimeSettings {
  provider: 'my_jarvis' | 'openai' | 'custom'
  llm_base_url: string
  llm_model: string
  llm_reasoning_effort: 'none' | null
  vision_use_same_model: boolean
  vision_model: string
  embedding_mode: 'auto' | 'separate' | 'disabled'
  embedding_base_url: string
  embedding_model: string
  embedding_auto_model: string
  llm_api_key_configured: boolean
  embedding_api_key_configured: boolean
  github_token_configured: boolean
  notion_token_configured: boolean
  qq_email_auth_code_configured: boolean
  weather_api_key_configured: boolean
  search_engine_url: string
  timezone: string
  max_history_messages: number
  assistant_style: 'concise' | 'balanced' | 'detailed'
  weather_base_url: string
  github_username: string
  qq_email_address: string
  needs_setup: boolean
  reindex: ReindexStatus
}

export interface SettingsUpdatePayload {
  provider: RuntimeSettings['provider']
  llm_base_url: string
  llm_model: string
  llm_reasoning_effort: 'none'
  vision_use_same_model: boolean
  vision_model: string
  embedding_mode: RuntimeSettings['embedding_mode']
  embedding_base_url: string
  embedding_model: string
  embedding_auto_model: string
  llm_api_key?: string
  embedding_api_key?: string
  github_token?: string
  notion_token?: string
  qq_email_auth_code?: string
  weather_api_key?: string
  clear_llm_api_key?: boolean
  clear_embedding_api_key?: boolean
  clear_github_token?: boolean
  clear_notion_token?: boolean
  clear_qq_email_auth_code?: boolean
  clear_weather_api_key?: boolean
  search_engine_url: string
  timezone: string
  max_history_messages: number
  assistant_style: 'concise' | 'balanced' | 'detailed'
  weather_base_url: string
  github_username: string
  qq_email_address: string
}

export async function fetchSettings(): Promise<RuntimeSettings> {
  const { data } = await api.get('/settings')
  return data
}

export async function saveSettings(payload: SettingsUpdatePayload): Promise<RuntimeSettings> {
  const { data } = await api.put('/settings', payload)
  return data
}

export async function discoverProviderModels(
  baseUrl: string,
  apiKey?: string,
): Promise<string[]> {
  const { data } = await api.post('/settings/models', {
    base_url: baseUrl,
    ...(apiKey ? { api_key: apiKey } : {}),
  })
  return data.models || []
}

export async function testProviderCapability(payload: {
  kind: 'chat' | 'vision' | 'embedding'
  base_url: string
  model: string
  api_key?: string
}): Promise<{ ok: boolean; checks: string[]; dimensions?: number }> {
  const { data } = await api.post('/settings/test', payload)
  return data
}

export async function startEmbeddingReindex(): Promise<ReindexStatus> {
  const { data } = await api.post('/settings/embedding/reindex')
  return data
}

export async function fetchEmbeddingReindex(): Promise<ReindexStatus> {
  const { data } = await api.get('/settings/embedding/reindex')
  return data
}

export interface MemoryItem {
  id: number
  content: string
  category: string
  importance: number
  source: string
  recall_count: number
  last_recalled_at?: string | null
  embedding_model?: string | null
  embedding_dimensions?: number | null
  created_at?: string | null
  updated_at?: string | null
}

export async function listMemories(params?: { q?: string; category?: string }): Promise<MemoryItem[]> {
  const { data } = await api.get('/memories', { params })
  return data
}

export async function createMemory(payload: Pick<MemoryItem, 'content' | 'category' | 'importance'>): Promise<MemoryItem> {
  const { data } = await api.post('/memories', payload)
  return data
}

export async function updateMemory(id: number, payload: Partial<Pick<MemoryItem, 'content' | 'category' | 'importance'>>): Promise<MemoryItem> {
  const { data } = await api.put(`/memories/${id}`, payload)
  return data
}

export async function deleteMemory(id: number): Promise<void> {
  await api.delete(`/memories/${id}`)
}

export async function exportMemories(): Promise<{ format: string; version: number; exported_at: string; memories: Array<Pick<MemoryItem, 'content' | 'category' | 'importance' | 'source'>> }> {
  const { data } = await api.get('/memories/export')
  return data
}

export async function importMemories(memories: Array<Pick<MemoryItem, 'content' | 'category' | 'importance' | 'source'>>): Promise<{ imported: number; skipped: number }> {
  const { data } = await api.post('/memories/import', { memories })
  return data
}

/** Combine two AbortSignals into one — aborts when either signal aborts. */
function combineAbortSignals(...signals: AbortSignal[]): AbortSignal {
  const controller = new AbortController()
  for (const sig of signals) {
    if (sig.aborted) {
      controller.abort(sig.reason)
      return controller.signal
    }
    sig.addEventListener('abort', () => controller.abort(sig.reason), { once: true })
  }
  return controller.signal
}

export interface FilePayload {
  name: string
  content: string  // base64-encoded content
  mime: string
}

/** Send a chat message and get the agent's reply. */
export async function sendChat(
  message: string,
  threadId?: string,
  images?: string[],
  files?: FilePayload[],
): Promise<string> {
  const payload: Record<string, any> = { message }
  if (threadId) {
    payload.thread_id = threadId
  }
  if (images && images.length > 0) {
    payload.images = images
  }
  if (files && files.length > 0) {
    payload.files = files
  }
  const { data } = await api.post('/chat', payload)
  return data.reply
}

/** Create a new conversation thread and return its ID. */
export async function createThread(title?: string): Promise<string> {
  const payload: Record<string, any> = {}
  if (title) payload.title = title
  const { data } = await api.post('/threads', payload)
  return data.id || data.thread_id
}

/** List all conversation threads (metadata only). */
export async function listThreads(): Promise<any[]> {
  const { data } = await api.get('/threads')
  return data
}

/** Get message history for a thread. */
export async function getThreadMessages(threadId: string): Promise<{ role: string; content: string }[]> {
  const { data } = await api.get(`/threads/${threadId}/messages`)
  return data.messages || []
}

export interface ThreadExport {
  format: 'hyperagent-thread-backup'
  version: number
  exported_at: string
  thread: {
    id: string
    title: string
    created_at: string
    updated_at: string
    message_count: number
    model: string
  }
  messages: Array<{ role: 'user' | 'assistant'; content: string }>
}

export async function exportThread(threadId: string): Promise<ThreadExport> {
  const { data } = await api.get(`/threads/${threadId}/export`)
  return data
}

/** Rename a thread. */
export async function renameThread(threadId: string, title: string): Promise<void> {
  await api.put(`/threads/${threadId}`, { title })
}

/** Delete a thread and its checkpoints. */
export async function deleteThread(threadId: string): Promise<void> {
  await api.delete(`/threads/${threadId}`)
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

/** List events for a month (YYYY-MM). */
export async function fetchEventsByMonth(month: string): Promise<EventItem[]> {
  const { data } = await api.get('/events', { params: { month } })
  return data
}

export interface ReminderItem {
  id: number
  title: string
  description: string
  trigger_at: string
  status: string
  event_id: number | null
}

export async function fetchReminders(): Promise<ReminderItem[]> {
  const { data } = await api.get('/reminders')
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
  images?: string[],
  files?: FilePayload[],
  signal?: AbortSignal,
): AsyncGenerator<string> {
  const payload: Record<string, any> = { message }
  if (threadId) payload.thread_id = threadId
  if (images && images.length > 0) payload.images = images
  if (files && files.length > 0) payload.files = files

  // 120s timeout for the initial response
  const controller = new AbortController()
  let timedOut = false
  const timeoutId = setTimeout(() => {
    timedOut = true
    controller.abort()
  }, 120_000)

  // Merge external signal with internal timeout
  const combinedSignal = signal
    ? combineAbortSignals(signal, controller.signal)
    : controller.signal

  let response: Response
  try {
    response = await fetch('/api/chat/stream', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
      signal: combinedSignal,
    })
  } catch (e: any) {
    clearTimeout(timeoutId)
    if (e?.name === 'AbortError') {
      if (timedOut) throw new Error('请求超时：模型服务在 120 秒内未开始响应')
      throw e
    }
    throw new Error('网络连接失败：请检查后端是否在运行')
  } finally {
    clearTimeout(timeoutId)
  }

  if (!response.ok) {
    let detail = ''
    try {
      const body = await response.json()
      if (typeof body?.detail === 'string') detail = body.detail
      else if (Array.isArray(body?.detail) && typeof body.detail[0]?.msg === 'string') {
        detail = body.detail[0].msg.replace(/^Value error,\s*/, '')
      }
    } catch { /* preserve the status fallback below */ }
    throw new Error(detail || `请求失败（HTTP ${response.status}）`)
  }

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
