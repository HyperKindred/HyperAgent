<script setup lang="ts">
import { ref, nextTick, onMounted } from 'vue'
import { marked } from 'marked'
import { sendChatStream } from '../api/client'
import { chatStore, initWelcomeMessage, clearChat } from '../store/chat'

const input = ref('')
const loading = ref(false)
const chatContainer = ref<HTMLDivElement | null>(null)
const pendingImages = ref<string[]>([])
const fileInput = ref<HTMLInputElement | null>(null)

const MAX_IMAGES = 3
const MAX_IMAGE_SIZE_MB = 5
const ACCEPTED_TYPES = ['image/png', 'image/jpeg', 'image/webp']

onMounted(() => {
  initWelcomeMessage()
  scrollToBottom()
})

async function handleNewChat() {
  await clearChat()
  initWelcomeMessage()
  pendingImages.value = []
  await nextTick()
  scrollToBottom()
}

// ── Image compression ────────────────────────────────────────────
function compressImage(file: File, maxSize = 1024, quality = 0.7): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader()
    reader.onerror = () => reject(new Error('Read failed'))
    reader.onload = () => {
      const img = new Image()
      img.onerror = () => reject(new Error('Decode failed'))
      img.onload = () => {
        let { width, height } = img
        if (width > height && width > maxSize) {
          height = Math.round(height * maxSize / width)
          width = maxSize
        } else if (height > maxSize) {
          width = Math.round(width * maxSize / height)
          height = maxSize
        }
        const canvas = document.createElement('canvas')
        canvas.width = width
        canvas.height = height
        const ctx = canvas.getContext('2d')
        if (!ctx) return reject(new Error('Canvas 2D unavailable'))
        ctx.drawImage(img, 0, 0, width, height)
        resolve(canvas.toDataURL('image/jpeg', quality))
      }
      img.src = reader.result as string
    }
    reader.readAsDataURL(file)
  })
}

async function handleFileSelect(e: Event) {
  const files = (e.target as HTMLInputElement).files
  if (!files) return
  for (const file of Array.from(files)) {
    if (!ACCEPTED_TYPES.includes(file.type)) continue
    if (file.size > MAX_IMAGE_SIZE_MB * 1024 * 1024) continue
    if (pendingImages.value.length >= MAX_IMAGES) break
    try {
      const b64 = await compressImage(file)
      pendingImages.value.push(b64)
    } catch { /* skip failed images */ }
  }
  if (fileInput.value) fileInput.value.value = ''
}

function handlePaste(e: ClipboardEvent) {
  const items = e.clipboardData?.items
  if (!items) return
  for (const item of Array.from(items)) {
    if (item.type.startsWith('image/')) {
      e.preventDefault()
      const file = item.getAsFile()
      if (!file) continue
      if (file.size > MAX_IMAGE_SIZE_MB * 1024 * 1024) continue
      if (pendingImages.value.length >= MAX_IMAGES) break
      compressImage(file).then(b64 => {
        if (pendingImages.value.length < MAX_IMAGES) {
          pendingImages.value.push(b64)
        }
      })
    }
  }
}

function removePendingImage(index: number) {
  pendingImages.value.splice(index, 1)
}

async function handleSend() {
  const text = input.value.trim()
  const hasImages = pendingImages.value.length > 0
  if ((!text && !hasImages) || loading.value) return

  const imagesToSend = hasImages ? [...pendingImages.value] : undefined

  chatStore.messages.push({
    role: 'user',
    content: text,
    images: imagesToSend,
  })
  input.value = ''
  pendingImages.value = []
  loading.value = true

  await nextTick()
  scrollToBottom()

  const msgIndex = chatStore.messages.length
  chatStore.messages.push({ role: 'assistant', content: '' })

  await nextTick()
  scrollToBottom()

  try {
    for await (const token of sendChatStream(text, chatStore.threadId, imagesToSend)) {
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

function renderMarkdown(text: string): string {
  const html = marked.parse(text, { breaks: true })
  return typeof html === 'string' ? html : ''
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
          <div v-if="msg.images && msg.images.length > 0" class="message-images">
            <img v-for="(img, j) in msg.images" :key="j" :src="img" class="msg-img" alt="图片" />
          </div>
          <div v-else-if="msg.hasImages" class="message-images">
            <div class="img-placeholder">🖼️ <span>图片</span></div>
          </div>
          <div class="message-content" :class="{ 'cursor-blink': loading && i === chatStore.messages.length - 1 && msg.content }">
            <div v-if="loading && i === chatStore.messages.length - 1 && !msg.content" class="typing-indicator">
              <span></span><span></span><span></span>
            </div>
            <div v-else v-html="renderMarkdown(msg.content)" />
          </div>
    </div>
    </div>

    </div>

    <div class="pending-images" v-if="pendingImages.length > 0">
      <div v-for="(img, i) in pendingImages" :key="'p'+i" class="pending-image-item">
        <img :src="img" class="pending-thumb" alt="待发送图片" />
        <button class="remove-img" @click="removePendingImage(i)" title="移除">&times;</button>
      </div>
      <span class="pending-hint">{{ pendingImages.length }}/{{ MAX_IMAGES }}</span>
    </div>

    <div class="chat-input-area">
      <label class="upload-btn" title="上传图片（或 Ctrl+V 粘贴）">
        <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/></svg>
        <input type="file" ref="fileInput" :accept="ACCEPTED_TYPES.join(',')" multiple hidden @change="handleFileSelect" />
      </label>
      <textarea
        v-model="input"
        class="chat-input"
        placeholder="输入你的问题... (Shift+Enter 换行，Enter 发送)"
        rows="2"
        :disabled="loading"
        @keydown="handleKeydown"
        @paste="handlePaste"
      ></textarea>
      <button
        class="send-btn"
        :disabled="(!input.trim() && pendingImages.length === 0) || loading"
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
  flex-direction: column;
  align-items: flex-end;
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

.message-images {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-bottom: 8px;
  max-width: 360px;
}

.msg-img {
  width: 100%;
  max-width: 240px;
  max-height: 180px;
  border-radius: 10px;
  object-fit: cover;
  border: 1px solid #e0e3e8;
}

.img-placeholder {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 4px 10px;
  background: #f0f1f5;
  border-radius: 6px;
  font-size: 12px;
  color: #999;
  margin-bottom: 6px;
}

.img-placeholder span {
  font-size: 12px;
  color: #999;
}

.pending-images {
  display: flex;
  gap: 10px;
  padding: 12px 28px 0;
  align-items: center;
  flex-shrink: 0;
}

.pending-image-item {
  position: relative;
}

.pending-thumb {
  width: 64px;
  height: 64px;
  border-radius: 8px;
  object-fit: cover;
  border: 1px solid #e0e3e8;
}

.remove-img {
  position: absolute;
  top: -6px;
  right: -6px;
  width: 18px;
  height: 18px;
  border-radius: 50%;
  border: none;
  background: #ef4444;
  color: #fff;
  font-size: 14px;
  line-height: 1;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 0;
}

.remove-img:hover {
  background: #dc2626;
}

.pending-hint {
  font-size: 12px;
  color: #999;
  margin-left: 4px;
}

.chat-input-area {
  padding: 12px 28px 24px;
  border-top: 1px solid #eef0f4;
  display: flex;
  gap: 10px;
  align-items: flex-end;
  flex-shrink: 0;
}

.upload-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 40px;
  height: 40px;
  border: 1px solid #e0e3e8;
  border-radius: 10px;
  background: #fff;
  color: #999;
  cursor: pointer;
  transition: all 0.15s;
  flex-shrink: 0;
}

.upload-btn:hover {
  background: #f0f1f5;
  color: #6366f1;
  border-color: #c7d2fe;
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

.message-content.cursor-blink::after {
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
