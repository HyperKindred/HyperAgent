<script setup lang="ts">
import { onMounted, ref, computed, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import {
  chatStore,
  loadThreadList,
  switchThread,
  clearChat,
  deleteThreadById,
  renameThreadById,
} from '../store/chat'
import { exportThread, fetchEventsByMonth, type EventItem } from '../api/client'
import { calendarChangeSignal } from '../store/calendar'
import { Brain, CalendarDays, Download, MessageSquare, Settings, Plus, Pencil, Trash2, ChevronLeft, ChevronRight } from '@lucide/vue'

const route = useRoute()
const router = useRouter()
const renaming = ref<string | null>(null)
const renameInput = ref('')
const confirmingDelete = ref<string | null>(null)

function isValidThreadId(id: unknown): id is string {
  return typeof id === 'string' && id.startsWith('hyperagent-')
}

// ── Calendar state (sidebar mini widget) ──────────────────────────
const currentMonth = ref(fmtMonth(new Date()))
const selectedDate = ref(fmtDate(new Date()))
const events = ref<EventItem[]>([])

function fmtDate(d: Date): string {
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
}
function fmtMonth(d: Date): string {
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}`
}

const weekdays = ['日', '一', '二', '三', '四', '五', '六']

const yearLabel = computed(() => {
  const [y, m] = currentMonth.value.split('-').map(Number)
  return `${y}年${m}月`
})

const calendarDays = computed(() => {
  const [y, m] = currentMonth.value.split('-').map(Number)
  const first = new Date(y, m - 1, 1)
  const last = new Date(y, m, 0)
  const startDow = first.getDay()
  const days: (number | null)[] = Array(startDow).fill(null)
  for (let d = 1; d <= last.getDate(); d++) days.push(d)
  return days
})

const eventDates = computed(() => {
  const s = new Set<string>()
  for (const e of events.value) {
    s.add(e.start_time.slice(0, 10))
  }
  return s
})

const currentRoute = computed(() => route.name)

async function loadMonth() {
  try {
    events.value = await fetchEventsByMonth(currentMonth.value)
  } catch {
    events.value = []
  }
}

function goMonth(delta: number) {
  const [y, m] = currentMonth.value.split('-').map(Number)
  const d = new Date(y, m - 1 + delta, 1)
  currentMonth.value = fmtMonth(d)
}

function selectDay(day: number | null) {
  if (day == null) return
  const [y, m] = currentMonth.value.split('-').map(Number)
  selectedDate.value = `${y}-${String(m).padStart(2, '0')}-${String(day).padStart(2, '0')}`
  // Navigate to calendar route with date param
  router.push({ name: 'calendar', query: { dt: selectedDate.value } })
}

function isToday(day: number | null) {
  if (day == null) return false
  const now = new Date()
  const today = fmtDate(now)
  const [y, m] = currentMonth.value.split('-').map(Number)
  return `${y}-${String(m).padStart(2, '0')}-${String(day).padStart(2, '0')}` === today
}

function isSelected(day: number | null) {
  if (day == null) return false
  const [y, m] = currentMonth.value.split('-').map(Number)
  return `${y}-${String(m).padStart(2, '0')}-${String(day).padStart(2, '0')}` === selectedDate.value
}

watch(currentMonth, loadMonth)

// Reload events when CalendarView changes data
watch(calendarChangeSignal, () => {
  if (currentRoute.value === 'calendar') {
    loadMonth()
  }
})

// ── Thread logic ──────────────────────────────────────────────────

onMounted(async () => {
  await loadThreadList()
  // Sync the selected date from the calendar route query on mount
  if (route.query.dt && typeof route.query.dt === 'string') {
    selectedDate.value = route.query.dt
    const match = route.query.dt.match(/^(\d{4}-\d{2})/)
    if (match) currentMonth.value = match[1]
  }
  if (currentRoute.value === 'calendar') await loadMonth()
})

// Watch for calendar route entries — reload events when navigated to
watch(() => route.name, async (name) => {
  if (name === 'calendar') {
    await loadMonth()
  }
})

function formatTime(iso: string | null | undefined): string {
  if (!iso) return ''
  const d = new Date(iso)
  if (isNaN(d.getTime())) return ''
  const now = new Date()
  const diffMs = now.getTime() - d.getTime()
  const diffMins = Math.floor(diffMs / 60000)
  if (diffMins < 1) return '刚刚'
  if (diffMins < 60) return `${diffMins}分钟前`
  const diffHours = Math.floor(diffMins / 60)
  if (diffHours < 24) return `${diffHours}小时前`
  const diffDays = Math.floor(diffHours / 24)
  if (diffDays < 7) return `${diffDays}天前`
  return `${d.getMonth() + 1}/${d.getDate()}`
}

async function handleClick(threadId: string) {
  if (!isValidThreadId(threadId)) return
  await switchThread(threadId)
}

async function handleNewChat() {
  await clearChat()
}

function startRename(e: MouseEvent, id: string, currentTitle: string) {
  e.stopPropagation()
  renaming.value = id
  renameInput.value = currentTitle
}

async function confirmRename(id: string) {
  const title = renameInput.value.trim()
  if (title) {
    await renameThreadById(id, title)
  }
  renaming.value = null
}

async function handleDelete(e: MouseEvent, id: string) {
  e.stopPropagation()
  confirmingDelete.value = id
}

async function confirmDelete(id: string) {
  await deleteThreadById(id)
  confirmingDelete.value = null
}

async function downloadThread(e: MouseEvent, id: string, title: string) {
  e.stopPropagation()
  try {
    const backup = await exportThread(id)
    const blob = new Blob([JSON.stringify(backup, null, 2)], { type: 'application/json' })
    const url = URL.createObjectURL(blob)
    const link = document.createElement('a')
    const safeTitle = title.replace(/[\\/:*?"<>|]/g, '_').slice(0, 80) || 'conversation'
    link.href = url
    link.download = `hyperagent-${safeTitle}.json`
    link.click()
    window.setTimeout(() => URL.revokeObjectURL(url), 0)
  } catch {
    window.alert('导出对话失败，请稍后重试')
  }
}
</script>

<template>
  <div class="sidebar">
    <!-- ── Main content area (scrollable, takes remaining space) ── -->
    <div class="sidebar-content">
      <!-- ── Chat mode: thread list ── -->
      <template v-if="currentRoute === 'chat'">
        <div class="chat-controls">
          <div class="brand">
            <span class="brand-icon">🤖</span>
            <span class="brand-name">HyperAgent</span>
          </div>
          <button class="new-chat-btn" @click="handleNewChat" title="新对话">
            <Plus :size="16" /> 新对话
          </button>
        </div>

        <div class="thread-list">
          <div
            v-for="thread in chatStore.threads"
            :key="thread.id"
            class="thread-item"
            :class="{ active: thread.id === chatStore.threadId }"
            @click="handleClick(thread.id)"
          >
            <template v-if="renaming === thread.id">
              <input
                v-model="renameInput"
                class="rename-input"
                @keyup.enter="confirmRename(thread.id)"
                @keyup.escape="renaming = null"
                @blur="confirmRename(thread.id)"
                autofocus
                @click.stop
              />
            </template>
            <template v-else>
              <div class="thread-title">{{ thread.title }}</div>
              <div class="thread-meta">
                <span class="thread-time">{{ formatTime(thread.updated_at) }}</span>
                <span class="thread-actions">
                  <button
                    class="action-btn"
                    title="重命名"
                    @click="(e) => startRename(e, thread.id, thread.title)"
                  ><Pencil :size="14" /></button>
                  <button
                    class="action-btn"
                    title="导出对话"
                    @click="(e) => downloadThread(e, thread.id, thread.title)"
                  ><Download :size="14" /></button>
                  <button
                    class="action-btn delete-btn"
                    title="删除"
                    @click="(e) => handleDelete(e, thread.id)"
                  ><Trash2 :size="14" /></button>
                </span>
              </div>
            </template>

            <!-- Delete confirmation -->
            <div v-if="confirmingDelete === thread.id" class="delete-confirm" @click.stop>
              <span>确定删除？</span>
              <button class="confirm-yes" @click="confirmDelete(thread.id)">是</button>
              <button class="confirm-no" @click="confirmingDelete = null">否</button>
            </div>
          </div>

          <div v-if="chatStore.threads.length === 0" class="empty-hint">
            暂无历史对话
          </div>
        </div>
      </template>

      <!-- ── Calendar mode: mini calendar widget ── -->
      <template v-if="currentRoute === 'calendar'">
        <div class="mini-calendar">
          <div class="mini-month-header">
            <button class="mini-nav-btn" @click="goMonth(-1)" title="上个月"><ChevronLeft :size="16" /></button>
            <span class="mini-month-title">{{ yearLabel }}</span>
            <button class="mini-nav-btn" @click="goMonth(1)" title="下个月"><ChevronRight :size="16" /></button>
          </div>

          <div class="mini-weekdays">
            <div v-for="d in weekdays" :key="d" class="mini-wd">{{ d }}</div>
          </div>

          <div class="mini-days">
            <div
              v-for="(day, i) in calendarDays"
              :key="i"
              class="mini-day"
              :class="{
                'day-off': day === null,
                'day-today': isToday(day),
                'day-sel': isSelected(day),
                'day-has-ev': day !== null && eventDates.has(
                  currentMonth.slice(0, 4) + '-' +
                  currentMonth.slice(5, 7) + '-' +
                  String(day).padStart(2, '0')
                ),
              }"
              @click="selectDay(day)"
            >
              {{ day ?? '' }}
            </div>
          </div>
        </div>
      </template>

      <template v-if="currentRoute === 'settings'">
        <div class="settings-context">
          <div class="brand">
            <span class="brand-icon">H</span>
            <span class="brand-name">HyperAgent</span>
          </div>
        </div>
      </template>
    </div>

    <!-- ── Tab navigation (always at bottom) ── -->
    <div class="sidebar-tabs">
      <router-link
        to="/"
        class="tab-btn"
        :class="{ active: currentRoute === 'chat' }"
      >
        <MessageSquare :size="18" />
        <span class="tab-label">对话</span>
      </router-link>
      <router-link
        to="/calendar"
        class="tab-btn"
        :class="{ active: currentRoute === 'calendar' }"
      >
        <CalendarDays :size="18" />
        <span class="tab-label">日程</span>
      </router-link>
      <router-link
        to="/memory"
        class="tab-btn"
        :class="{ active: currentRoute === 'memory' }"
        title="记忆"
      >
        <Brain :size="18" />
        <span class="tab-label">记忆</span>
      </router-link>
      <router-link
        to="/settings"
        class="tab-btn"
        :class="{ active: currentRoute === 'settings' }"
        title="设置"
      >
        <Settings :size="18" />
        <span class="tab-label">设置</span>
      </router-link>
    </div>
  </div>
</template>

<style scoped>
.sidebar {
  width: 240px;
  height: 100vh;
  background: #1a1a2e;
  color: #e0e0e0;
  display: flex;
  flex-direction: column;
  flex-shrink: 0;
  overflow: hidden;
}

/* ── Content area (fills space above tabs) ── */
.sidebar-content {
  flex: 1;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  min-height: 0;
}

/* ── Tab buttons (always at bottom) ── */
.sidebar-tabs {
  display: flex;
  border-top: 1px solid rgba(255, 255, 255, 0.08);
  flex-shrink: 0;
}

.tab-btn {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 2px;
  padding: 12px 0 10px;
  text-decoration: none;
  color: #808098;
  font-size: 11px;
  transition: all 0.15s;
  cursor: pointer;
  border-bottom: 2px solid transparent;
}

.tab-btn:hover {
  color: #c0c0e0;
  background: rgba(255, 255, 255, 0.04);
}

.tab-btn.active {
  color: #6366f1;
  border-bottom-color: #6366f1;
}

.tab-icon {
  font-size: 20px;
  line-height: 1;
}

.tab-label {
  font-weight: 600;
}

/* ── Chat controls (brand + new chat button) ── */
.chat-controls {
  padding: 12px 16px;
  border-bottom: 1px solid rgba(255, 255, 255, 0.08);
  flex-shrink: 0;
}

.brand {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 10px;
}

.brand-icon {
  font-size: 22px;
}

.brand-name {
  font-size: 16px;
  font-weight: 700;
  color: #fff;
}

.new-chat-btn {
  width: 100%;
  padding: 8px 12px;
  border: 1px dashed rgba(255, 255, 255, 0.2);
  border-radius: 8px;
  background: transparent;
  color: #a0a0c0;
  font-size: 13px;
  cursor: pointer;
  transition: all 0.2s;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
}

.settings-context { padding: 16px; }
.settings-context .brand-icon {
  width: 26px;
  height: 26px;
  border-radius: 6px;
  background: #2f6fed;
  color: #fff;
  display: grid;
  place-items: center;
  font-size: 13px;
  font-weight: 700;
}

.new-chat-btn:hover {
  background: rgba(255, 255, 255, 0.06);
  color: #fff;
  border-color: rgba(255, 255, 255, 0.4);
}

/* ── Thread list ── */
.thread-list {
  flex: 1;
  overflow-y: auto;
  padding: 8px;
}

.thread-item {
  position: relative;
  padding: 10px 12px;
  border-radius: 8px;
  cursor: pointer;
  transition: background 0.15s;
  margin-bottom: 2px;
}

.thread-item:hover {
  background: rgba(255, 255, 255, 0.06);
}

.thread-item.active {
  background: rgba(99, 102, 241, 0.15);
  border-left: 3px solid #6366f1;
}

.thread-title {
  font-size: 13px;
  font-weight: 600;
  color: #e0e0e0;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  margin-bottom: 2px;
}

.thread-meta {
  display: flex;
  justify-content: space-between;
  align-items: center;
  font-size: 11px;
  color: #808098;
}

.thread-actions {
  display: none;
  gap: 2px;
}

.thread-item:hover .thread-actions {
  display: flex;
}

.action-btn {
  background: none;
  border: none;
  cursor: pointer;
  font-size: 11px;
  padding: 2px 4px;
  border-radius: 4px;
  opacity: 0.6;
  transition: opacity 0.15s;
}

.action-btn:hover {
  opacity: 1;
  background: rgba(255, 255, 255, 0.1);
}

.delete-btn:hover {
  background: rgba(239, 68, 68, 0.2);
}

.rename-input {
  width: 100%;
  padding: 4px 8px;
  border: 1px solid #6366f1;
  border-radius: 4px;
  background: rgba(255, 255, 255, 0.08);
  color: #fff;
  font-size: 13px;
  outline: none;
}

.delete-confirm {
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  background: rgba(30, 30, 50, 0.95);
  border-radius: 8px;
  font-size: 13px;
}

.delete-confirm button {
  padding: 4px 12px;
  border: none;
  border-radius: 4px;
  cursor: pointer;
  font-size: 12px;
}

.confirm-yes {
  background: #ef4444;
  color: #fff;
}

.confirm-no {
  background: rgba(255, 255, 255, 0.1);
  color: #e0e0e0;
}

.empty-hint {
  text-align: center;
  color: #606080;
  font-size: 12px;
  padding: 24px 0;
}

/* ── Mini calendar widget ── */
.mini-calendar {
  padding: 16px;
  display: flex;
  flex-direction: column;
}

.mini-month-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 12px;
}

.mini-month-title {
  font-size: 14px;
  font-weight: 600;
  color: #e0e0e0;
}

.mini-nav-btn {
  background: none;
  border: 1px solid rgba(255, 255, 255, 0.12);
  border-radius: 6px;
  color: #808098;
  cursor: pointer;
  padding: 4px 8px;
  font-size: 11px;
  transition: all 0.15s;
}

.mini-nav-btn:hover {
  background: rgba(255, 255, 255, 0.08);
  color: #e0e0e0;
}

.mini-weekdays {
  display: grid;
  grid-template-columns: repeat(7, 1fr);
  margin-bottom: 4px;
}

.mini-wd {
  text-align: center;
  font-size: 10px;
  font-weight: 600;
  color: #606080;
  padding: 4px 0;
}

.mini-days {
  display: grid;
  grid-template-columns: repeat(7, 1fr);
  gap: 2px;
}

.mini-day {
  aspect-ratio: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 6px;
  cursor: pointer;
  font-size: 12px;
  transition: all 0.12s;
  position: relative;
  color: #c0c0d0;
}

.mini-day:hover:not(.day-off) {
  background: rgba(255, 255, 255, 0.08);
}

.day-off {
  cursor: default;
}

.day-today {
  color: #818cf8;
  font-weight: 700;
}

.day-sel {
  background: #059669 !important;
  color: #fff;
  font-weight: 600;
}

.day-has-ev::after {
  content: '';
  position: absolute;
  bottom: 3px;
  left: 50%;
  transform: translateX(-50%);
  width: 4px;
  height: 4px;
  border-radius: 50%;
  background: #6366f1;
}

.day-sel::after {
  background: #fff;
}
</style>
