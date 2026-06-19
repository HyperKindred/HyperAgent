<script setup lang="ts">
import { ref, nextTick, onMounted, computed } from 'vue'
import { marked } from 'marked'
import DOMPurify from 'dompurify'
import { sendChatStream, createThread } from '../api/client'
import { chatStore, initWelcomeMessage, loadThreadList } from '../store/chat'
import { MessageSquare, Send, Square, Paperclip, FileText, Code, File, X, Image as ImageIcon } from '@lucide/vue'

const input = ref('')
const loading = ref(false)
const abortRef = ref<AbortController | null>(null)
const chatContainer = ref<HTMLDivElement | null>(null)
const pendingImages = ref<string[]>([])
const pendingFiles = ref<{ name: string; content: string; mime: string }[]>([])
const fileInput = ref<HTMLInputElement | null>(null)

const MAX_IMAGES = 3
const MAX_FILE_SIZE_MB = 5
const MAX_FILES = 5
const ACCEPT_ALL = '.png,.jpg,.jpeg,.webp,.pdf,.docx,.doc,.txt,.md,.py,.js,.ts,.json,.csv,.html,.css,.yaml,.yml,.xml,.ini,.cfg,.log,.sh,.bat,.env'

const hasInput = computed(() => input.value.trim().length > 0 || pendingImages.value.length > 0 || pendingFiles.value.length > 0)

onMounted(() => {
  initWelcomeMessage()
  scrollToBottom()
})

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

function isImageFile(file: File): boolean {
  // Check MIME type first, then fall back to extension
  if (file.type.startsWith('image/')) return true
  const imgExts = ['.png', '.jpg', '.jpeg', '.webp', '.gif', '.bmp', '.svg']
  const ext = '.' + (file.name.split('.').pop() || '').toLowerCase()
  return imgExts.includes(ext)
}

async function handleFileSelect(e: Event) {
  const files = (e.target as HTMLInputElement).files
  if (!files) return
  for (const file of Array.from(files)) {
    if (file.size > MAX_FILE_SIZE_MB * 1024 * 1024) {
      alert(`文件 "${file.name}" 超过 ${MAX_FILE_SIZE_MB}MB，已跳过`)
      continue
    }
    if (isImageFile(file)) {
      if (pendingImages.value.length >= MAX_IMAGES) break
      try {
        const b64 = await compressImage(file)
        pendingImages.value.push(b64)
      } catch { /* skip */ }
    } else {
      if (pendingFiles.value.length >= MAX_FILES) {
        alert(`最多同时上传 ${MAX_FILES} 个文件`)
        break
      }
      try {
        const dataUrl = await readFileAsBase64(file)
        pendingFiles.value.push({ name: file.name, content: dataUrl.split(',')[1] || dataUrl, mime: file.type })
      } catch { /* skip */ }
    }
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
      if (file.size > MAX_FILE_SIZE_MB * 1024 * 1024) continue
      if (pendingImages.value.length >= MAX_IMAGES) break
      compressImage(file).then(b64 => {
        if (pendingImages.value.length < MAX_IMAGES) pendingImages.value.push(b64)
      })
    }
  }
}

function removePendingImage(index: number) {
  pendingImages.value.splice(index, 1)
}

function readFileAsBase64(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader()
    reader.onerror = () => reject(new Error('Read failed'))
    reader.onload = () => resolve(reader.result as string)
    reader.readAsDataURL(file)
  })
}

function removePendingFile(index: number) {
  pendingFiles.value.splice(index, 1)
}

function getFileIcon(name: string): any {
  const ext = name.split('.').pop()?.toLowerCase()
  switch (ext) {
    case 'pdf': return FileText
    case 'docx':
    case 'doc': return FileText
    case 'txt':
    case 'md': return FileText
    case 'py':
    case 'js':
    case 'ts':
    case 'json':
    case 'css':
    case 'html': return Code
    default: return File
  }
}

/** Ensure a thread appears in the sidebar, deduping by id. */
function _ensureThreadInList(id: string, title: string) {
  if (chatStore.threads.some(t => t.id === id)) return
  chatStore.threads.unshift({
    id,
    title,
    created_at: new Date().toISOString(),
    updated_at: new Date().toISOString(),
    message_count: 0,
  })
}

async function handleSend() {
  const text = input.value.trim()
  const hasImages = pendingImages.value.length > 0
  const hasFiles = pendingFiles.value.length > 0
  if ((!text && !hasImages && !hasFiles) || loading.value) return

  // Auto-create a thread if none exists (e.g. after deleting all threads)
  if (!chatStore.threadId) {
    try {
      const newId = await createThread()
      chatStore.threadId = newId
      localStorage.setItem('hyperagent-thread', newId)
    } catch {
      // API failed — use a local-only thread ID so the conversation still works
      chatStore.threadId = `hyperagent-${Date.now().toString(36)}`
      localStorage.setItem('hyperagent-thread', chatStore.threadId)
    }
    // Ensure the thread appears in the sidebar immediately.
    // The finally block also calls loadThreadList() as a safety net.
    _ensureThreadInList(chatStore.threadId, '新对话')
  }

  const imagesToSend = hasImages ? [...pendingImages.value] : undefined
  const filesToSend = hasFiles ? [...pendingFiles.value] : undefined

  chatStore.messages.push({
    role: 'user',
    content: text,
    images: imagesToSend,
    files: filesToSend,
  })
  input.value = ''
  pendingImages.value = []
  pendingFiles.value = []
  loading.value = true

  await nextTick()
  scrollToBottom()

  const msgIndex = chatStore.messages.length
  chatStore.messages.push({ role: 'assistant', content: '' })

  await nextTick()
  scrollToBottom()

  // Create a new AbortController for this request
  const controller = new AbortController()
  abortRef.value = controller

  try {
    for await (const token of sendChatStream(text, chatStore.threadId, imagesToSend, filesToSend, controller.signal)) {
      chatStore.messages[msgIndex].content += token
      await nextTick()
      scrollToBottom()
    }
  } catch (e: any) {
    // Ignore abort errors (user clicked stop)
    if (e.name === 'AbortError') return
    const msg = e.message || ''
    if (msg.includes('abort') || msg.includes('timed out')) {
      chatStore.messages[msgIndex].content = '❌ 请求超时：后端处理时间过长，请重试或检查 Vite 代理是否正常'
    } else {
      chatStore.messages[msgIndex].content = '❌ 请求失败：' + msg
    }
  } finally {
    loading.value = false
    // Refresh sidebar ordering — this thread's updated_at just changed
    await loadThreadList()
    await nextTick()
    scrollToBottom()
  }
}

function scrollToBottom() {
  if (chatContainer.value) {
    chatContainer.value.scrollTop = chatContainer.value.scrollHeight
  }
}

function stopStreaming() {
  if (abortRef.value) {
    abortRef.value.abort()
    abortRef.value = null
  }
  loading.value = false
}

function handleKeydown(e: KeyboardEvent) {
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault()
    handleSend()
  }
}

function renderMarkdown(text: string): string {
  // Escape `---` horizontal rules so they don't create intrusive <hr> lines
  const safe = text.replace(/\n---+\n/g, '\n——\n')
  const html = marked.parse(safe, { breaks: true })
  // Sanitize to prevent XSS (agent content is LLM-generated, but the
  // LLM could be prompted to produce raw HTML/script tags)
  const raw = typeof html === 'string' ? html : ''
  return DOMPurify.sanitize(raw)
}

function autoResize(e: Event) {
  const el = e.target as HTMLTextAreaElement
  el.style.height = 'auto'
  el.style.height = Math.min(el.scrollHeight, 270) + 'px'
}
</script>

<template>
  <div class="chat-page">
    <!-- Header -->
    <div class="chat-header">
      <h2><MessageSquare :size="20" /> 对话</h2>
    </div>

    <!-- Messages -->
    <div class="chat-messages" ref="chatContainer">
      <div class="messages-inner">
        <div
          v-for="(msg, i) in chatStore.messages"
          :key="i"
          class="message"
          :class="msg.role"
        >
          <div class="message-avatar">
            <img
              v-if="msg.role === 'user'"
              src="/avatars/user.png"
              alt="用户"
              class="avatar-img"
            />
            <img
              v-else
              src="/avatars/agent.png"
              alt="HyperAgent"
              class="avatar-img agent-avatar"
            />
          </div>
          <div class="message-body">
            <div v-if="msg.images && msg.images.length > 0" class="message-images">
              <img v-for="(img, j) in msg.images" :key="j" :src="img" class="msg-img" alt="图片" />
            </div>
            <div v-else-if="msg.hasImages" class="message-images">
              <div class="img-placeholder"><ImageIcon :size="14" /> <span>图片</span></div>
            </div>
            <div v-if="msg.fileInfo && msg.fileInfo.length > 0" class="message-files">
              <div v-for="(f, j) in msg.fileInfo" :key="'fi'+j" class="file-badge">
                <component :is="getFileIcon(f.name)" :size="14" />
                <span>{{ f.name }}</span>
              </div>
            </div>
            <div v-else-if="msg.files && msg.files.length > 0" class="message-files">
              <div v-for="(f, j) in msg.files" :key="'ff'+j" class="file-badge">
                <component :is="getFileIcon(f.name)" :size="14" />
                <span>{{ f.name }}</span>
              </div>
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
    </div>

    <!-- Pending file previews -->
    <div class="pending-previews" v-if="pendingImages.length > 0 || pendingFiles.length > 0">
      <div v-for="(img, i) in pendingImages" :key="'p'+i" class="pending-image-item">
        <img :src="img" class="pending-thumb" alt="待发送图片" />
        <button class="remove-btn" @click="removePendingImage(i)" title="移除"><X :size="12" /></button>
      </div>
      <div v-for="(f, i) in pendingFiles" :key="'pf'+i" class="pending-file-item">
        <component :is="getFileIcon(f.name)" :size="16" />
        <span class="pending-file-name">{{ f.name }}</span>
        <button class="remove-btn" @click="removePendingFile(i)" title="移除"><X :size="12" /></button>
      </div>
    </div>

    <!-- Input area -->
    <div class="chat-input-area" :class="{ 'has-input': hasInput }">
      <div class="input-wrapper">
        <textarea
          v-model="input"
          class="chat-input"
          placeholder="输入你的问题... (Shift+Enter 换行，Enter 发送)"
          rows="1"
          :disabled="loading"
          @keydown="handleKeydown"
          @paste="handlePaste"
          @input="autoResize"
        ></textarea>
      </div>
      <div class="input-actions">
        <label class="action-btn upload-btn" title="上传文件或图片">
          <Paperclip :size="20" />
          <input type="file" ref="fileInput" :accept="ACCEPT_ALL" multiple hidden @change="handleFileSelect" />
        </label>
        <button
          class="action-btn"
          :class="loading ? 'stop-btn' : 'send-btn'"
          :disabled="loading ? false : !hasInput"
          @click="loading ? stopStreaming() : handleSend()"
          :title="loading ? '停止' : '发送'"
        >
          <component :is="loading ? Square : Send" :size="20" />
        </button>
      </div>
    </div>
  </div>
</template>

<style scoped>
/* ── Layout ─────────────────────────────────────────────── */
.chat-page {
  display: flex;
  flex-direction: column;
  height: 100vh;
  background: #fff;
}

/* ── Header ─────────────────────────────────────────────── */
.chat-header {
  padding: 16px 28px;
  border-bottom: 1px solid #eef0f4;
  flex-shrink: 0;
}

.chat-header h2 {
  margin: 0;
  font-size: 18px;
  font-weight: 600;
  display: flex;
  align-items: center;
  gap: 8px;
  color: #1f2937;
}

/* ── Messages ───────────────────────────────────────────── */
.chat-messages {
  flex: 1;
  overflow-y: auto;
  padding: 0;
}

.messages-inner {
  max-width: 800px;
  margin: 0 auto;
  padding: 24px 28px;
}

.message {
  display: flex;
  gap: 14px;
  margin-bottom: 24px;
  animation: fadeIn 0.2s ease-out;
}

.message.user {
  flex-direction: row-reverse;
}

@keyframes fadeIn {
  from { opacity: 0; transform: translateY(6px); }
  to   { opacity: 1; transform: translateY(0); }
}

.message-avatar {
  width: 32px;
  height: 32px;
  border-radius: 50%;
  flex-shrink: 0;
  overflow: hidden;
  margin-top: 4px;
}

.avatar-img {
  width: 100%;
  height: 100%;
  object-fit: cover;
  display: block;
}

.agent-avatar {
  object-fit: contain;
  padding: 0;
  transform: scale(1.15);
}

.message-body {
  max-width: 75%;
  min-width: 0;
}

.message.user .message-body {
  display: flex;
  flex-direction: column;
  align-items: flex-end;
}

.message-content {
  padding: 12px 18px;
  border-radius: 18px;
  font-size: 15px;
  line-height: 1.65;
  word-break: break-word;
}

.message.assistant .message-content {
  background: #f2f3f7;
  color: #1f2937;
  border-bottom-left-radius: 6px;
}

.message.user .message-content {
  background: #6366f1;
  color: #fff;
  border-bottom-right-radius: 6px;
}

/* ── Images / files in messages ─────────────────────────── */
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
  border-radius: 12px;
  object-fit: cover;
  border: 1px solid #e5e7eb;
}

.img-placeholder {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 4px 10px;
  background: #f3f4f6;
  border-radius: 6px;
  font-size: 12px;
  color: #9ca3af;
  margin-bottom: 6px;
}

.img-placeholder span {
  font-size: 12px;
  color: #9ca3af;
}

.message-files {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-bottom: 8px;
}

.file-badge {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 3px 10px;
  background: #f3f4f6;
  border-radius: 6px;
  font-size: 12px;
  color: #6b7280;
}

.file-badge span {
  max-width: 180px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

/* ── Pending previews (between messages & input) ──────────── */
.pending-previews {
  display: flex;
  gap: 10px;
  padding: 0 28px 8px;
  align-items: center;
  flex-shrink: 0;
  flex-wrap: wrap;
  max-width: 800px;
  margin: 0 auto;
  width: 100%;
}

.pending-image-item {
  position: relative;
}

.pending-thumb {
  width: 64px;
  height: 64px;
  border-radius: 8px;
  object-fit: cover;
  border: 1px solid #e5e7eb;
}

.pending-file-item {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 6px 10px;
  background: #f3f4f6;
  border-radius: 8px;
  font-size: 13px;
  color: #6b7280;
  position: relative;
}

.pending-file-name {
  max-width: 140px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.remove-btn {
  position: absolute;
  top: -7px;
  right: -7px;
  width: 18px;
  height: 18px;
  border-radius: 50%;
  border: none;
  background: #ef4444;
  color: #fff;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 0;
  transition: background 0.15s;
}

.remove-btn:hover { background: #dc2626; }

/* ── Input area ──────────────────────────────────────────── */
.chat-input-area {
  padding: 0 28px 16px;
  flex-shrink: 0;
}

.input-wrapper {
  max-width: 800px;
  margin: 0 auto;
  width: 100%;
  background: #fff;
  border: 1.5px solid #d1d5db;
  border-radius: 14px;
  transition: border-color 0.2s, box-shadow 0.2s;
  overflow: hidden;
}

.input-wrapper:focus-within {
  border-color: #6366f1;
  box-shadow: 0 0 0 3px rgba(99, 102, 241, 0.12);
}

.chat-input {
  width: 100%;
  padding: 14px 18px;
  border: none;
  outline: none;
  font-size: 15px;
  font-family: inherit;
  line-height: 1.6;
  resize: none;
  background: transparent;
  color: #1f2937;
  min-height: 26px;
  max-height: 270px; /* ~8 lines */
}

.chat-input::placeholder {
  color: #9ca3af;
}

.chat-input:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

/* ── Input action buttons ───────────────────────────────── */
.input-actions {
  max-width: 800px;
  margin: 8px auto 0;
  width: 100%;
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.action-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 36px;
  height: 36px;
  border-radius: 10px;
  border: none;
  cursor: pointer;
  transition: all 0.15s;
  flex-shrink: 0;
  background: transparent;
  color: #9ca3af;
}

.upload-btn:hover {
  background: #f3f4f6;
  color: #6366f1;
}

.send-btn {
  background: #6366f1;
  color: #fff;
}

.send-btn:hover:not(:disabled) {
  background: #4f46e5;
}

.send-btn:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}

.stop-btn {
  background: #ef4444;
  color: #fff;
}

.stop-btn:hover {
  background: #dc2626;
}

.chat-input-area.has-input .send-btn:not(:disabled) {
  opacity: 1;
}
</style>

<style>
/* ── Global markdown content styles ──────────────────────── */
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
  border-radius: 10px;
  overflow-x: auto;
  margin: 8px 0;
}
.message-content pre code { background: none; padding: 0; }
.message-content blockquote {
  border-left: 3px solid #6366f1;
  margin: 8px 0;
  padding: 4px 12px;
  color: #6b7280;
}
.message-content ul, .message-content ol { padding-left: 20px; margin: 6px 0; }
.message-content a { color: #6366f1; text-decoration: none; }
.message-content a:hover { text-decoration: underline; }
.message-content table { border-collapse: collapse; margin: 8px 0; font-size: 0.9em; }
.message-content th, .message-content td { border: 1px solid #ddd; padding: 6px 10px; }
.message-content th { background: #f0f1f5; font-weight: 600; }
.message-content p { margin: 6px 0; }
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
  gap: 5px;
  padding: 14px 16px;
}

.typing-indicator span {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: #c4c8d4;
  animation: typing 1.4s infinite both;
}

.typing-indicator span:nth-child(2) { animation-delay: 0.2s; }
.typing-indicator span:nth-child(3) { animation-delay: 0.4s; }

@keyframes typing {
  0%, 60%, 100% { transform: translateY(0); }
  30% { transform: translateY(-6px); }
}
</style>
