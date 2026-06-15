<script setup lang="ts">
import { ref, onMounted, onUnmounted } from 'vue'
import { useRouter } from 'vue-router'

interface Toast {
  id: number
  title: string
  body: string
  eventType: string
  visible: boolean
  navTarget?: string // route to navigate to on click
}

const router = useRouter()
const toasts = ref<Toast[]>([])
let eventSource: EventSource | null = null
let toastIdCounter = 0

function getNavTarget(eventType: string): string {
  switch (eventType) {
    case 'reminder': return '/'
    case 'suggestion': return '/'
    case 'third_party': return '/'
    case 'calendar': return '/calendar'
    default: return '/'
  }
}

function getEventColor(eventType: string): string {
  switch (eventType) {
    case 'reminder': return '#6366f1'  // indigo
    case 'suggestion': return '#f59e0b' // amber
    case 'third_party': return '#10b981' // emerald
    case 'calendar': return '#3b82f6'   // blue
    default: return '#6366f1'
  }
}

function getEventIcon(eventType: string): string {
  switch (eventType) {
    case 'reminder': return '⏰'
    case 'suggestion': return '💡'
    case 'third_party': return '🔔'
    case 'calendar': return '📅'
    default: return '🔔'
  }
}

function handleToastClick(toast: Toast) {
  // Navigate to the target route
  if (toast.navTarget) {
    router.push(toast.navTarget)
  }
  // Dismiss immediately
  toast.visible = false
  setTimeout(() => {
    toasts.value = toasts.value.filter(t => t.id !== toast.id)
  }, 300)
}

function showToast(title: string, body: string, eventType: string = 'reminder') {
  const id = ++toastIdCounter
  const toast: Toast = {
    id,
    title,
    body,
    eventType,
    visible: true,
    navTarget: getNavTarget(eventType),
  }
  toasts.value.push(toast)

  // Try Electron native notification first
  if (window.electronAPI?.showNotification) {
    window.electronAPI.showNotification({ title, body })
  }

  // Auto-remove after 5 seconds
  setTimeout(() => {
    toast.visible = false
    setTimeout(() => {
      toasts.value = toasts.value.filter(t => t.id !== id)
    }, 300)
  }, 5000)
}

onMounted(() => {
  eventSource = new EventSource('/api/notifications/stream')

  eventSource.onmessage = (event) => {
    try {
      const data = JSON.parse(event.data)
      if (data.event_type) {
        showToast(data.title, data.body, data.event_type)
      }
    } catch {
      // Ignore non-JSON messages (like keepalive)
    }
  }

  eventSource.onerror = () => {
    console.warn('[notifications] SSE connection lost, reconnecting...')
  }
})

onUnmounted(() => {
  eventSource?.close()
  eventSource = null
})
</script>

<template>
  <Teleport to="body">
    <div class="toast-container">
      <TransitionGroup name="toast">
        <div
          v-for="toast in toasts"
          :key="toast.id"
          class="toast-item"
          :class="{ 'toast-hide': !toast.visible }"
          :style="{ '--accent': getEventColor(toast.eventType) }"
          @click="handleToastClick(toast)"
        >
          <div class="toast-accent"></div>
          <div class="toast-icon">{{ getEventIcon(toast.eventType) }}</div>
          <div class="toast-content">
            <div class="toast-title">{{ toast.title }}</div>
            <div class="toast-body" v-if="toast.body !== toast.title">
              {{ toast.body }}
            </div>
            <div class="toast-hint">点击查看</div>
          </div>
        </div>
      </TransitionGroup>
    </div>
  </Teleport>
</template>

<style scoped>
.toast-container {
  position: fixed;
  top: 16px;
  right: 16px;
  z-index: 9999;
  display: flex;
  flex-direction: column;
  gap: 8px;
  pointer-events: none;
}

.toast-item {
  display: flex;
  gap: 12px;
  background: #fff;
  border: 1px solid #e8eaef;
  border-radius: 12px;
  padding: 14px 18px 14px 0;
  min-width: 300px;
  max-width: 420px;
  box-shadow: 0 6px 20px rgba(0, 0, 0, 0.10), 0 1px 4px rgba(0, 0, 0, 0.06);
  pointer-events: auto;
  cursor: pointer;
  transition: all 0.35s cubic-bezier(0.34, 1.56, 0.64, 1);
  overflow: hidden;
  position: relative;
}

.toast-item:hover {
  transform: translateX(-4px);
  box-shadow: 0 8px 28px rgba(0, 0, 0, 0.14), 0 2px 8px rgba(0, 0, 0, 0.08);
}

.toast-item.toast-hide {
  opacity: 0;
  transform: translateX(100%);
  pointer-events: none;
}

.toast-accent {
  width: 4px;
  flex-shrink: 0;
  background: var(--accent);
  margin-right: 4px;
}

.toast-icon {
  font-size: 24px;
  line-height: 1.3;
  flex-shrink: 0;
}

.toast-content {
  flex: 1;
  min-width: 0;
}

.toast-title {
  font-weight: 600;
  font-size: 14px;
  color: #1f2937;
  margin-bottom: 2px;
  line-height: 1.4;
}

.toast-body {
  font-size: 13px;
  color: #6b7280;
  word-break: break-word;
  line-height: 1.4;
}

.toast-hint {
  font-size: 11px;
  color: var(--accent);
  margin-top: 4px;
  opacity: 0;
  transition: opacity 0.2s;
}

.toast-item:hover .toast-hint {
  opacity: 0.8;
}

/* TransitionGroup animations */
.toast-enter-active {
  transition: all 0.35s cubic-bezier(0.34, 1.56, 0.64, 1);
}

.toast-leave-active {
  transition: all 0.25s ease-in;
}

.toast-enter-from {
  opacity: 0;
  transform: translateX(100%) scale(0.9);
}

.toast-leave-to {
  opacity: 0;
  transform: translateX(100%) scale(0.9);
}
</style>
