<script setup lang="ts">
import { ref, nextTick, onMounted } from 'vue'
import { marked } from 'marked'
import { sendChatStream } from '../api/client'
import { chatStore, initWelcomeMessage, clearChat } from '../store/chat'

const input = ref('')
const loading = ref(false)
const chatContainer = ref<HTMLDivElement | null>(null)

onMounted(() => {
  initWelcomeMessage()
  scrollToBottom()
})

async function handleNewChat() {
  await clearChat()
  initWelcomeMessage()
  await nextTick()
  scrollToBottom()
}

async function handleSend() {
  const text = input.value.trim()
  if (!text || loading.value) return

  chatStore.messages.push({ role: 'user', content: text })
  input.value = ''
  loading.value = true

  await nextTick()
  scrollToBottom()

  // pre-fill empty assistant message, append tokens one by one
  const msgIndex = chatStore.messages.length
  chatStore.messages.push({ role: 'assistant', content: '' })

  await nextTick()
  scrollToBottom()

  try {
    for await (const token of sendChatStream(text, chatStore.threadId)) {
      chatStore.messages[msgIndex].content += token
      await nextTick()
      scrollToBottom()
    }
  } catch (e: any) {
    chatStore.messages[msgIndex].content =
      '❌ 请求失败：' + (e.message || '请确认后端服务是否已启动')
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
  return marked.parse(text, { breaks: true })
}
</script>

<template>
  <div class="chat-page">
    <div class="chat-header">
      <h2>💬 对话</h2>
      <button class="btn-new-chat" @click="handleNewChat" title="开启新对话（清空本地显示）">
        ✨ 新对话
      </button>
    </div>

    <div class="chat-messages" ref="chatContainer">
      <div
        v-for="(msg, i) in chatStore.messages"
        :key="i"
        class="message"
        :class="msg.role"
      >
        <div class="message-avatar">
          {{ msg.role === 'user' ? '👤' : '🤖' }}
        </div>
        <div class="message-body">
          <div class="message-content" :class="{ streaming: loading && i === chatStore.messages.length - 1 }" v-html="renderMarkdown(msg.content)" />
        </div>
      </div>

      <div v-if="loading && chatStore.messages.length > 0 && chatStore.messages[chatStore.messages.length - 1].content === ''" class="message assistant">
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
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.chat-header h2 {
  margin: 0;
  font-size: 20px;
  font-weight: 600;
}

.btn-new-chat {
  padding: 6px 14px;
  background: transparent;
  color: #999;
  border: 1px solid #e0e3e8;
  border-radius: 6px;
  font-size: 13px;
  cursor: pointer;
  transition: all 0.15s;
}

.btn-new-chat:hover {
  background: #f0f1f5;
  color: #6366f1;
  border-color: #c7d2fe;
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

<style>
.message-content code {
  background: #f0f0f3;
  padding: 2px 6px;
  border-radius: 4px;
  font-family: "SF Mono", "Fira Code", monospace;
  font-size: 0.9em;
}
.message-content pre {
  background: #f4f5f9;
  padding: 12px 16px;
  border-radius: 8px;
  overflow-x: auto;
  margin: 8px 0;
}
.message-content pre code { background: none; padding: 0; }
.message-content blockquote {
  border-left: 3px solid #6366f1;
  margin: 8px 0;
  padding: 4px 12px;
  color: #666;
}
.message-content ul, .message-content ol { padding-left: 20px; margin: 6px 0; }
.message-content a { color: #6366f1; text-decoration: none; }
.message-content a:hover { text-decoration: underline; }
.message-content table { border-collapse: collapse; margin: 8px 0; font-size: 0.9em; }
.message-content th, .message-content td { border: 1px solid #ddd; padding: 6px 10px; }
.message-content th { background: #f0f1f5; font-weight: 600; }
.message-content p { margin: 4px 0; }
.message-content strong { font-weight: 600; }

.message-content.streaming::after {
  content: "|";
  animation: blink 0.8s step-end infinite;
  color: #6366f1;
  font-weight: bold;
  margin-left: 1px;
}

@keyframes blink {
  0%, 100% { opacity: 1; }
  50% { opacity: 0; }
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
</style>



