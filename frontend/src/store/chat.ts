import { reactive, watch } from 'vue'
import { createThread } from '../api/client'

export interface Message {
  role: 'user' | 'assistant'
  content: string
}

interface ChatStore {
  messages: Message[]
  threadId: string
}

const STORAGE_KEY = 'hyperagent-chat'
const MAX_STORED = 100  // 最多持久化 100 条，避免 localStorage 过大

/** 共享的对话状态 —— 页面切换不丢失，刷新后自动恢复最近消息 */
export const chatStore = reactive<ChatStore>({
  messages: loadMessages(),
  threadId: loadThreadId(),
})

// 每次消息变化自动保存到 localStorage
watch(
  () => chatStore.messages,
  () => saveMessages(chatStore.messages),
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
  // 如果从 localStorage 恢复的已有消息，不重复注入
  if (chatStore.messages.length > 0) return
  chatStore.messages.push({
    role: 'assistant',
    content: pickGreeting(),
  })
}

// ── localStorage helpers ────────────────────────────────────────────

function loadMessages(): Message[] {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    if (!raw) return []
    const parsed = JSON.parse(raw)
    if (Array.isArray(parsed)) return parsed.slice(-MAX_STORED)
  } catch {
    // corrupted data — start fresh
  }
  return []
}

function saveMessages(msgs: Message[]) {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(msgs.slice(-MAX_STORED)))
  } catch {
    // localStorage full — silently ignore
  }
}

/** 清空前端显示 + localStorage（线程级别的 /new 操作） */
export async function clearChat() {
  try {
    const newId = await createThread()
    chatStore.threadId = newId
    localStorage.setItem(THREAD_STORAGE_KEY, newId)
  } catch {
    // API 不可用时回退到本地时间戳（仍然创建新 ID）
    chatStore.threadId = `hyperagent-${Date.now().toString(36)}`
  }
  chatStore.messages.splice(0)
  try { localStorage.removeItem(STORAGE_KEY) } catch {}
  _initialized = false
}


// ── thread_id localStorage helpers ──────────────────────────────────

const THREAD_STORAGE_KEY = 'hyperagent-thread'

function loadThreadId(): string {
  try {
    return localStorage.getItem(THREAD_STORAGE_KEY) || 'hyperagent-main'
  } catch {
    return 'hyperagent-main'
  }
}




