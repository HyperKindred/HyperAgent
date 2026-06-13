<script setup lang="ts">
import { ref, nextTick, onMounted } from 'vue'
import { sendChat } from '../api/client'

interface Message {
  role: 'user' | 'assistant'
  content: string
}

const messages = ref<Message[]>([])
const input = ref('')
const loading = ref(false)
const chatContainer = ref<HTMLDivElement | null>(null)

onMounted(() => {
  messages.value.push({
    role: 'assistant',
    content: `你好！我是 HyperAgent，你的个人 AI 助手。我可以帮你管理日程：

- 📅 **加日程**：加日程：明天下午3点开会
- 🔍 **查日程**：今天有什么安排？
- ✏️ **改日程**：把会议改到下午4点
- ❌ **删日程**：删除 ID 为 1 的日程

有什么我可以帮你的吗？`,
  })
})

async function handleSend() {
  const text = input.value.trim()
  if (!text || loading.value) return

  messages.value.push({ role: 'user', content: text })
  input.value = ''
  loading.value = true

  await nextTick()
  scrollToBottom()

  try {
    const reply = await sendChat(text)
    messages.value.push({ role: 'assistant', content: reply })
  } catch (e: any) {
    messages.value.push({
      role: 'assistant',
      content: `❌ 请求失败：${e.message || '请确认后端服务是否已启动（uv run uvicorn app.main:app --port 8000）'}`,
    })
  } finally {
    loading.value = false
    await nextTick()
    scrollToBottom()
  }
}

function scrollToBottom() {
  if (chatContainer.value) {
    chatContainer.value.scrollTop = chatContainer.value.scrollHeight
  }
}

function handleKeydown(e: KeyboardEvent) {
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault()
    handleSend()
  }
}

/** Simple markdown-like rendering */
function renderMarkdown(text: string): string {
  return text
    .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
    .replace(/\n/g, '<br>')
}
</script>

<template>
  <div class="chat-page">
    <div class="chat-header">
      <h2>💬 对话</h2>
    </div>

    <div class="chat-messages" ref="chatContainer">
      <div
        v-for="(msg, i) in messages"
        :key="i"
        class="message"
        :class="msg.role"
      >
        <div class="message-avatar">
          {{ msg.role === 'user' ? '👤' : '🤖' }}
        </div>
        <div class="message-body">
          <div class="message-content" v-html="renderMarkdown(msg.content)" />
        </div>
      </div>

      <div v-if="loading" class="message assistant">
        <div class="message-avatar">🤖</div>
        <div class="message-body">
          <div class="typing-indicator">
            <span></span><span></span><span></span>
          </div>
        </div>
      </div>
    </div>

    <div class="chat-input-area">
      <textarea
        v-model="input"
        class="chat-input"
        placeholder="输入你的问题... (Shift+Enter 换行，Enter 发送)"
        rows="2"
        :disabled="loading"
        @keydown="handleKeydown"
      ></textarea>
      <button
        class="send-btn"
        :disabled="!input.trim() || loading"
        @click="handleSend"
      >
        <span v-if="!loading">发送</span>
        <span v-else>思考中...</span>
      </button>
    </div>
  </div>
</template>

<style scoped>
.chat-page {
  display: flex;
  flex-direction: column;
  height: 100vh;
  background: #fff;
}

.chat-header {
  padding: 20px 28px 16px;
  border-bottom: 1px solid #eef0f4;
  flex-shrink: 0;
}

.chat-header h2 {
  margin: 0;
  font-size: 20px;
  font-weight: 600;
}

.chat-messages {
  flex: 1;
  overflow-y: auto;
  padding: 20px 28px;
}

.message {
  display: flex;
  gap: 12px;
  margin-bottom: 20px;
}

.message.user {
  flex-direction: row-reverse;
}

.message-avatar {
  width: 36px;
  height: 36px;
  border-radius: 50%;
  background: #f0f1f5;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 18px;
  flex-shrink: 0;
}

.message-body {
  max-width: 75%;
}

.message.user .message-body {
  display: flex;
  justify-content: flex-end;
}

.message-content {
  padding: 12px 16px;
  border-radius: 12px;
  font-size: 15px;
  line-height: 1.65;
  word-break: break-word;
}

.message.assistant .message-content {
  background: #f4f5f9;
  color: #333;
  border-bottom-left-radius: 4px;
}

.message.user .message-content {
  background: #6366f1;
  color: #fff;
  border-bottom-right-radius: 4px;
}

.typing-indicator {
  display: flex;
  gap: 4px;
  padding: 12px 16px;
  background: #f4f5f9;
  border-radius: 12px;
  border-bottom-left-radius: 4px;
}

.typing-indicator span {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: #ccc;
  animation: typing 1.4s infinite both;
}

.typing-indicator span:nth-child(2) { animation-delay: 0.2s; }
.typing-indicator span:nth-child(3) { animation-delay: 0.4s; }

@keyframes typing {
  0%, 60%, 100% { transform: translateY(0); }
  30% { transform: translateY(-6px); }
}

.chat-input-area {
  padding: 16px 28px 24px;
  border-top: 1px solid #eef0f4;
  display: flex;
  gap: 12px;
  align-items: flex-end;
  flex-shrink: 0;
}

.chat-input {
  flex: 1;
  padding: 12px 16px;
  border: 1px solid #e0e3e8;
  border-radius: 10px;
  font-size: 15px;
  font-family: inherit;
  resize: none;
  outline: none;
  transition: border-color 0.15s;
}

.chat-input:focus {
  border-color: #6366f1;
}

.send-btn {
  padding: 12px 24px;
  background: #6366f1;
  color: #fff;
  border: none;
  border-radius: 10px;
  font-size: 15px;
  font-weight: 500;
  cursor: pointer;
  transition: background 0.15s;
  flex-shrink: 0;
}

.send-btn:hover:not(:disabled) {
  background: #4f46e5;
}

.send-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}
</style>
