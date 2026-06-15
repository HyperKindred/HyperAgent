<script setup lang="ts">
import { ref, onMounted, computed, watch } from 'vue'
import {
  fetchEventsByMonth,
  fetchEvents,
  fetchReminders,
  deleteEvent,
  createEvent,
  type EventItem,
  type ReminderItem,
} from '../api/client'
import { CalendarDays, ChevronLeft, ChevronRight, Bell, Plus, X, Trash2 } from '@lucide/vue'

// ── State ──────────────────────────────────────────────────────────
const events = ref<EventItem[]>([])
const reminders = ref<ReminderItem[]>([])
const loading = ref(false)
const currentMonth = ref(fmtMonth(new Date()))
const selectedDate = ref(fmtDate(new Date()))
const showAddForm = ref(false)
const delConfirmId = ref<number | null>(null)

// Add form
const newTitle = ref('')
const newTime = ref('09:00')
const newEndTime = ref('')
const newDesc = ref('')
const newPriority = ref('normal')
const addError = ref('')

// ── Helpers ────────────────────────────────────────────────────────
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

/** Days in the current month with leading blanks for the first weekday. */
const calendarDays = computed(() => {
  const [y, m] = currentMonth.value.split('-').map(Number)
  const first = new Date(y, m - 1, 1)
  const last = new Date(y, m, 0)
  const startDow = first.getDay() // 0=Sun
  const days: (number | null)[] = Array(startDow).fill(null)
  for (let d = 1; d <= last.getDate(); d++) days.push(d)
  return days
})

/** Set of date strings (YYYY-MM-DD) that have events. */
const eventDates = computed(() => {
  const s = new Set<string>()
  for (const e of events.value) {
    s.add(e.start_time.slice(0, 10))
  }
  return s
})

/** Reminders keyed by event_id. */
const reminderByEventId = computed(() => {
  const m = new Map<number, ReminderItem>()
  for (const r of reminders.value) {
    if (r.event_id != null && r.status === 'pending') m.set(r.event_id, r)
  }
  return m
})

const dayEvents = computed(() =>
  events.value.filter(e => e.start_time.startsWith(selectedDate.value))
)

// ── Data loading ───────────────────────────────────────────────────
async function loadMonth() {
  loading.value = true
  try {
    const [evts, rems] = await Promise.all([
      fetchEventsByMonth(currentMonth.value),
      fetchReminders(),
    ])
    events.value = evts
    reminders.value = rems
  } catch {
    events.value = []
    reminders.value = []
  } finally {
    loading.value = false
  }
}

function goMonth(delta: number) {
  const [y, m] = currentMonth.value.split('-').map(Number)
  const d = new Date(y, m - 1 + delta, 1)
  // Use local date formatting to avoid UTC timezone shift
  const yy = d.getFullYear()
  const mm = String(d.getMonth() + 1).padStart(2, '0')
  currentMonth.value = `${yy}-${mm}`
}

function selectDay(day: number | null) {
  if (day == null) return
  const [y, m] = currentMonth.value.split('-').map(Number)
  selectedDate.value = `${y}-${String(m).padStart(2, '0')}-${String(day).padStart(2, '0')}`
}

function isToday(day: number | null) {
  if (day == null) return false
  const now = new Date()
  const today = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}-${String(now.getDate()).padStart(2, '0')}`
  const [y, m] = currentMonth.value.split('-').map(Number)
  return `${y}-${String(m).padStart(2, '0')}-${String(day).padStart(2, '0')}` === today
}

function isSelected(day: number | null) {
  if (day == null) return false
  const [y, m] = currentMonth.value.split('-').map(Number)
  return `${y}-${String(m).padStart(2, '0')}-${String(day).padStart(2, '0')}` === selectedDate.value
}

// ── CRUD ───────────────────────────────────────────────────────────

async function handleDelete(id: number) {
  try {
    await deleteEvent(id)
    events.value = events.value.filter(e => e.id !== id)
    delConfirmId.value = null
  } catch {}
}

async function handleAdd() {
  if (!newTitle.value.trim()) {
    addError.value = '请输入标题'
    return
  }
  addError.value = ''
  const startTime = `${selectedDate.value}T${newTime.value}:00`
  const endTime = newEndTime.value ? `${selectedDate.value}T${newEndTime.value}:00` : undefined
  try {
    await createEvent({
      title: newTitle.value.trim(),
      start_time: startTime,
      end_time: endTime,
      description: newDesc.value.trim(),
      priority: newPriority.value,
    })
    showAddForm.value = false
    newTitle.value = ''
    newTime.value = '09:00'
    newEndTime.value = ''
    newDesc.value = ''
    newPriority.value = 'normal'
    await loadMonth()
  } catch {}
}

const priorityLabel = (p: string) =>
  ({ low: '低', normal: '普通', high: '高' } as Record<string, string>)[p] || p
const statusLabel = (s: string) =>
  ({ pending: '待办', completed: '完成', cancelled: '取消' } as Record<string, string>)[s] || s

onMounted(loadMonth)
watch(currentMonth, loadMonth)
</script>

<template>
  <div class="calendar-page">
    <div class="calendar-layout">
      <!-- ── Left: Events for selected day ── -->
      <div class="events-panel">
        <div class="events-panel-header">
          <h3>{{ selectedDate }}</h3>
          <button class="add-btn-icon" @click="showAddForm = !showAddForm" title="添加日程">
            <Plus :size="20" />
          </button>
        </div>

        <!-- Quick add form -->
        <div v-if="showAddForm" class="add-form" @click.stop>
          <div class="form-row">
            <input v-model="newTitle" class="form-input full" placeholder="标题" @keyup.enter="handleAdd" />
          </div>
          <div class="form-row inline">
            <input v-model="newTime" type="time" class="form-input" />
            <span class="form-sep">→</span>
            <input v-model="newEndTime" type="time" class="form-input" placeholder="结束" />
            <select v-model="newPriority" class="form-input">
              <option value="low">低</option>
              <option value="normal">普通</option>
              <option value="high">高</option>
            </select>
          </div>
          <div class="form-row">
            <input v-model="newDesc" class="form-input full" placeholder="描述（可选）" />
          </div>
          <div v-if="addError" class="form-error">{{ addError }}</div>
          <button class="btn-primary" @click="handleAdd">确认</button>
        </div>

        <!-- Events -->
        <div v-if="dayEvents.length > 0" class="events-list">
          <div
            v-for="event in dayEvents"
            :key="'e' + event.id"
            class="event-card"
            :class="'priority-' + event.priority"
          >
            <div class="event-left">
              <div class="event-time">{{ event.start_time.slice(11, 16) }}</div>
              <div v-if="event.end_time" class="event-time end">
                {{ event.end_time.slice(11, 16) }}
              </div>
            </div>
            <div class="event-main">
              <div class="event-title-row">
                <span class="event-title">{{ event.title }}</span>
                <span v-if="reminderByEventId.has(event.id)" class="reminder-badge" title="已设置提醒">
                  <Bell :size="14" />
                </span>
              </div>
              <div class="event-meta">
                <span class="event-priority" :class="'prio-' + event.priority">
                  {{ priorityLabel(event.priority) }}
                </span>
                <span class="event-status">{{ statusLabel(event.status) }}</span>
              </div>
              <div v-if="event.description" class="event-desc">{{ event.description }}</div>
            </div>
            <button
              class="event-delete"
              :title="delConfirmId === event.id ? '再次点击确认删除' : '删除'"
              @click="delConfirmId === event.id ? handleDelete(event.id) : (delConfirmId = event.id)"
            >
              <Trash2 v-if="delConfirmId !== event.id" :size="16" />
              <span v-else class="confirm-text">确认？</span>
            </button>
          </div>
        </div>

        <!-- Standalone reminders removed — reminders only appear as 🔔 on events -->

        <div v-if="dayEvents.length === 0" class="empty-state">
          <div class="empty-icon">📭</div>
          <p>没有日程安排</p>
        </div>
      </div>

      <!-- ── Right: Calendar grid ── -->
      <div class="calendar-panel">
        <div class="month-header">
          <h2 class="month-title">
            <CalendarDays :size="22" />
            {{ yearLabel }}
          </h2>
          <div class="month-nav">
            <button class="nav-btn" @click="goMonth(-1)" title="上个月"><ChevronLeft :size="20" /></button>
            <button class="nav-btn" @click="currentMonth = fmtMonth(new Date())" title="今天">今天</button>
            <button class="nav-btn" @click="goMonth(1)" title="下个月"><ChevronRight :size="20" /></button>
          </div>
        </div>

        <div class="weekday-row">
          <div v-for="d in weekdays" :key="d" class="weekday-cell">{{ d }}</div>
        </div>

        <div class="days-grid">
          <div
            v-for="(day, i) in calendarDays"
            :key="i"
            class="day-cell"
            :class="{
              'day-empty': day === null,
              'day-today': isToday(day),
              'day-selected': isSelected(day),
              'day-has-event': day !== null && eventDates.has(
                currentMonth.slice(0, 4) + '-' +
                currentMonth.slice(5, 7) + '-' +
                String(day).padStart(2, '0')
              ),
            }"
            @click="selectDay(day)"
          >
            <span class="day-num">{{ day ?? '' }}</span>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.calendar-page {
  height: 100vh;
  background: #fff;
  overflow: hidden;
}

.calendar-layout {
  display: flex;
  height: 100%;
}

/* ── Right calendar panel ────────────────────────────────────────── */
.calendar-panel {
  width: 360px;
  flex-shrink: 0;
  padding: 20px;
  margin: 20px;
  border: 1px solid #eef0f4;
  border-radius: 16px;
  background: #fafbfd;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  gap: 2px;
  align-self: flex-start;
}

.month-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 16px;
}

.month-title {
  font-size: 18px;
  font-weight: 600;
  color: #1f2937;
  display: flex;
  align-items: center;
  gap: 8px;
  margin: 0;
}

.month-nav {
  display: flex;
  gap: 4px;
  align-items: center;
}

.nav-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 5px 8px;
  border: 1px solid #e5e7eb;
  border-radius: 6px;
  background: #fff;
  color: #6b7280;
  font-size: 12px;
  cursor: pointer;
  transition: all 0.15s;
}

.nav-btn:hover {
  background: #f3f4f6;
  color: #6366f1;
  border-color: #c7d2fe;
}

.weekday-row {
  display: grid;
  grid-template-columns: repeat(7, 1fr);
  margin-bottom: 4px;
}

.weekday-cell {
  text-align: center;
  font-size: 12px;
  font-weight: 600;
  color: #9ca3af;
  padding: 6px 0;
}

.days-grid {
  display: grid;
  grid-template-columns: repeat(7, 1fr);
  gap: 2px;
}

.day-cell {
  aspect-ratio: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 8px;
  cursor: pointer;
  font-size: 14px;
  transition: all 0.12s;
  position: relative;
}

.day-cell:hover:not(.day-empty) {
  background: #f3f4f6;
}

.day-num {
  z-index: 1;
}

.day-empty {
  cursor: default;
}

.day-today .day-num {
  color: #6366f1;
  font-weight: 700;
}

.day-selected {
  background: #059669 !important;
  color: #fff;
  font-weight: 600;
}

.day-selected:hover {
  background: #047857 !important;
}

.day-has-event .day-num::after {
  content: '';
  position: absolute;
  bottom: 5px;
  left: 50%;
  transform: translateX(-50%);
  width: 5px;
  height: 5px;
  border-radius: 50%;
  background: #6366f1;
}

.day-selected .day-num::after {
  background: #fff;
}

/* Add form */
.add-form {
  margin-top: 12px;
  padding: 14px;
  background: #f9fafb;
  border: 1px solid #e5e7eb;
  border-radius: 10px;
}

.form-row { margin-bottom: 8px; }
.form-row.inline { display: flex; gap: 6px; align-items: center; }
.form-input {
  padding: 7px 10px;
  border: 1px solid #d1d5db;
  border-radius: 6px;
  font-size: 13px;
  font-family: inherit;
  outline: none;
}
.form-input:focus { border-color: #6366f1; }
.form-input.full { width: 100%; box-sizing: border-box; }
.form-sep { color: #9ca3af; font-size: 13px; }
.form-error { color: #ef4444; font-size: 12px; margin-bottom: 6px; }
.btn-primary {
  width: 100%;
  padding: 8px;
  background: #6366f1;
  color: #fff;
  border: none;
  border-radius: 8px;
  font-size: 13px;
  cursor: pointer;
}
.btn-primary:hover { background: #4f46e5; }

/* ── Right events panel ──────────────────────────────────────────── */
.events-panel {
  flex: 1;
  padding: 28px 32px;
  overflow-y: auto;
  min-width: 0;
}

.events-panel-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 20px;
}

.events-panel-header h3 {
  margin: 0;
  font-size: 16px;
  font-weight: 600;
  color: #374151;
}

.add-btn-icon {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 36px;
  height: 36px;
  border-radius: 50%;
  border: 1px solid #e5e7eb;
  background: #fff;
  color: #6b7280;
  cursor: pointer;
  transition: all 0.15s;
}

.add-btn-icon:hover {
  background: #f3f4f6;
  color: #6366f1;
  border-color: #c7d2fe;
}

.events-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.event-card {
  display: flex;
  gap: 14px;
  padding: 14px 16px;
  border-radius: 12px;
  border: 1px solid #eef1f6;
  background: #fafbfd;
  transition: box-shadow 0.15s;
}

.event-card:hover {
  box-shadow: 0 2px 10px rgba(0,0,0,0.06);
}

.event-card.priority-high { border-left: 3px solid #ef4444; }
.event-card.priority-normal { border-left: 3px solid #f59e0b; }
.event-card.priority-low { border-left: 3px solid #63e29c; }

.event-left {
  flex-shrink: 0;
  width: 48px;
  text-align: center;
  padding-top: 2px;
}

.event-time {
  font-size: 15px;
  font-weight: 700;
  color: #1f2937;
}

.event-time.end {
  font-size: 12px;
  font-weight: 400;
  color: #9ca3af;
  margin-top: 2px;
}

.event-main { flex: 1; min-width: 0; }

.event-title-row {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-bottom: 4px;
}

.event-title {
  font-size: 15px;
  font-weight: 600;
  color: #1f2937;
}

.reminder-badge {
  display: inline-flex;
  align-items: center;
  color: #059669;
  flex-shrink: 0;
}

.event-meta {
  display: flex;
  gap: 10px;
  margin-bottom: 2px;
}

.event-priority,
.event-status {
  font-size: 12px;
  color: #9ca3af;
}

.event-priority.prio-high { color: #ef4444; }
.event-priority.prio-normal { color: #f59e0b; }
.event-priority.prio-low { color: #63e29c; }

.event-desc {
  font-size: 13px;
  color: #9ca3af;
  margin-top: 4px;
  line-height: 1.4;
}

.event-delete {
  flex-shrink: 0;
  background: none;
  border: none;
  cursor: pointer;
  padding: 4px 6px;
  border-radius: 6px;
  color: #d1d5db;
  transition: all 0.15s;
  align-self: flex-start;
}

.event-delete:hover {
  background: #fef2f2;
  color: #ef4444;
}

.confirm-text {
  font-size: 11px;
  font-weight: 600;
  color: #ef4444;
  white-space: nowrap;
}

.empty-state {
  text-align: center;
  padding: 60px 20px;
  color: #9ca3af;
}

.empty-icon { font-size: 40px; margin-bottom: 10px; }
.empty-state p { margin: 4px 0; font-size: 14px; }
</style>
