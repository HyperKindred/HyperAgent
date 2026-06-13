import { reactive, watch } from 'vue'

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
  threadId: 'hyperagent-main',
})

// 每次消息变化自动保存到 localStorage
watch(
  () => chatStore.messages.length,
  () => saveMessages(chatStore.messages),
)

/** 仅在首次挂载时注入欢迎消息 */
let _initialized = false

export function initWelcomeMessage() {
  if (_initialized) return
  _initialized = true
  // 如果从 localStorage 恢复的已有消息，不重复注入
  if (chatStore.messages.length > 0) return
  chatStore.messages.push({
    role: 'assistant',
    content: `你好！我是 HyperAgent，你的个人 AI 助手。我可以帮你管理日程：

- 📅 **加日程**：加日程：明天下午3点开会
- 🔍 **查日程**：今天有什么安排？
- ✏️ **改日程**：把会议改到下午4点
- ❌ **删日程**：删除 ID 为 1 的日程

有什么我可以帮你的吗？`,
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
export function clearChat() {
  chatStore.messages.splice(0)
  try { localStorage.removeItem(STORAGE_KEY) } catch {}
  _initialized = false
}
