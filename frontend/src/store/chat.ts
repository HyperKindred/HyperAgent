import { reactive, watch } from 'vue'
import { createThread, listThreads, getThreadMessages, deleteThread as apiDeleteThread, renameThread as apiRenameThread } from '../api/client'

export interface FileAttachment {
  name: string
  content: string  // base64 — not persisted to localStorage
  mime: string
}

/** Persisted file metadata — name & type survive page refresh. */
export interface FileInfo {
  name: string
  mime: string
}

export interface Message {
  role: 'user' | 'assistant'
  content: string
  /** Base64 images — only kept in memory during the session. */
  images?: string[]
  /** Uploaded files — only kept in memory during the session. */
  files?: FileAttachment[]
  /** Persisted flag: true if this message originally had images. */
  hasImages?: boolean
  /** Persisted file info (name + mime only) — survives page refresh. */
  fileInfo?: FileInfo[]
}

export interface ThreadMeta {
  id: string
  title: string
  created_at: string
  updated_at: string
  message_count: number
}

interface ChatStore {
  messages: Message[]
  threadId: string
  threads: ThreadMeta[]
}

const MAX_STORED = 100  // max messages per thread

function messagesStorageKey(threadId: string): string {
  return `hyperagent-chat-${threadId}`
}

const THREAD_STORAGE_KEY = 'hyperagent-thread'

/** 共享的对话状态 —— 页面切换不丢失，刷新后自动恢复最近消息 */
export const chatStore = reactive<ChatStore>({
  messages: loadMessagesForThread(loadThreadId()),
  threadId: loadThreadId(),
  threads: [],
})

// Auto-save messages on every change (debounced to avoid spamming
// localStorage on every streaming token).
let _saveTimer: ReturnType<typeof setTimeout> | null = null
watch(
  () => chatStore.messages,
  () => {
    if (_saveTimer) clearTimeout(_saveTimer)
    _saveTimer = setTimeout(() => {
      saveMessagesForThread(chatStore.threadId, chatStore.messages)
      _saveTimer = null
    }, 500)
  },
  { deep: true },
)

/** 仅在首次挂载时注入欢迎消息 */
let _initialized = false

function pickGreeting(): string {
  const hour = new Date().getHours()
  if (hour < 6) return '睡不着吗 🌙'
  if (hour < 9) return '早啊 🌅 今天有什么计划？'
  if (hour < 12) return '上午好 ☀️'
  if (hour < 14) return '中午好 🌤️ 吃了吗？'
  if (hour < 18) return '下午好 🌤️'
  return '晚上好 🌙 今天过得怎么样？'
}

export function initWelcomeMessage() {
  if (_initialized) return
  _initialized = true
  if (chatStore.messages.length > 0) return
  chatStore.messages.push({
    role: 'assistant',
    content: pickGreeting(),
  })
}

// ── Thread management ───────────────────────────────────────────────

/** Thread IDs always start with ``hyperagent-`` — reject anything else. */
function isValidThreadId(id: unknown): id is string {
  return typeof id === 'string' && id.startsWith('hyperagent-')
}

export async function loadThreadList() {
  try {
    const list = await listThreads()
    // Filter out threads with invalid IDs (e.g. corrupted "undefined" strings)
    chatStore.threads = (list || []).filter((t: any) => t && isValidThreadId(t.id))
  } catch {
    // Offline — keep existing list
  }
}

export async function switchThread(threadId: string) {
  if (!isValidThreadId(threadId)) return
  if (threadId === chatStore.threadId) return

  // Save current thread messages
  saveMessagesForThread(chatStore.threadId, chatStore.messages)

  // Switch
  chatStore.threadId = threadId
  localStorage.setItem(THREAD_STORAGE_KEY, threadId)

  // Load target thread messages (from cache or API)
  const cached = loadMessagesForThread(threadId)
  if (cached.length > 0) {
    chatStore.messages = cached
    _initialized = chatStore.messages.length > 0
  } else {
    // Fetch from backend
    try {
      const history = await getThreadMessages(threadId)
      chatStore.messages = history.length > 0
        ? history as Message[]
        : []
      // Cache them
      saveMessagesForThread(threadId, chatStore.messages)
    } catch {
      chatStore.messages = []
    }
    _initialized = chatStore.messages.length > 0
  }

  // Inject welcome if empty
  if (chatStore.messages.length === 0) {
    _initialized = false
    initWelcomeMessage()
  }

  // Refresh thread list
  await loadThreadList()
}

export async function clearChat() {
  const oldId = chatStore.threadId  // save before overwriting
  try {
    const newId = await createThread()
    chatStore.threadId = newId
    localStorage.setItem(THREAD_STORAGE_KEY, newId)
  } catch {
    chatStore.threadId = `hyperagent-${Date.now().toString(36)}`
  }
  chatStore.messages.splice(0)
  removeMessagesForThread(chatStore.threadId)
  // Clear localStorage for old thread ID to prevent stale message cache
  if (oldId) removeMessagesForThread(oldId)
  _initialized = false
  initWelcomeMessage()
  await loadThreadList()
}

export async function deleteThreadById(threadId: string) {
  if (!isValidThreadId(threadId)) return
  try {
    await apiDeleteThread(threadId)
  } catch {
    // Ignore if already deleted
  }
  removeMessagesForThread(threadId)
  chatStore.threads = chatStore.threads.filter(t => t.id !== threadId)

  // If we deleted the current thread, switch to the most recent one
  if (threadId === chatStore.threadId) {
    const next = chatStore.threads[0]
    if (next) {
      await switchThread(next.id)
    } else {
      // All threads deleted → show fresh welcome without creating a thread.
      // A new thread will be auto-created on first message send.
      chatStore.threadId = ''
      localStorage.removeItem(THREAD_STORAGE_KEY)
      chatStore.messages.splice(0)
      removeMessagesForThread(threadId)
      _initialized = false
      initWelcomeMessage()
    }
  }
}

export async function renameThreadById(threadId: string, title: string) {
  if (!isValidThreadId(threadId)) return
  try {
    await apiRenameThread(threadId, title)
    // Refresh ordering — other threads may have been touched since
    await loadThreadList()
  } catch {
    // Ignore
  }
}

// ── localStorage helpers (per-thread) ──────────────────────────────

function loadMessagesForThread(threadId: string): Message[] {
  try {
    const raw = localStorage.getItem(messagesStorageKey(threadId))
    if (!raw) return []
    const parsed = JSON.parse(raw)
    if (Array.isArray(parsed)) return parsed.slice(-MAX_STORED)
  } catch {
    // corrupted data
  }
  return []
}

function saveMessagesForThread(threadId: string, msgs: Message[]) {
  try {
    const stripped = msgs.map(({ images, files, ...rest }) => {
      const out: Record<string, any> = { ...rest }
      if (images && images.length > 0) out.hasImages = true
      if (files && files.length > 0) {
        out.fileInfo = files.map(({ name, mime }) => ({ name, mime }))
      }
      return out as Message
    })
    localStorage.setItem(messagesStorageKey(threadId), JSON.stringify(stripped.slice(-MAX_STORED)))
  } catch {
    // localStorage full
  }
}

function removeMessagesForThread(threadId: string) {
  try { localStorage.removeItem(messagesStorageKey(threadId)) } catch {}
}

function loadThreadId(): string {
  try {
    return localStorage.getItem(THREAD_STORAGE_KEY) || ''
  } catch {
    return ''
  }
}
