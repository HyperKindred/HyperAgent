<script setup lang="ts">
import { ref, onMounted, computed } from 'vue'
import { fetchEvents, deleteEvent, createEvent, type EventItem } from '../api/client'

const events = ref<EventItem[]>([])
const loading = ref(false)
const selectedDate = ref(new Date().toISOString().slice(0, 10))
const showAddForm = ref(false)
const delConfirmId = ref<number | null>(null)

// Add form
const newTitle = ref('')
const newTime = ref('09:00')
const newEndTime = ref('')
const newDesc = ref('')
const newPriority = ref('normal')
const addError = ref('')

const priorityLabel = (p: string) =>
  ({ low: '🟢 低', normal: '🟡 普通', high: '🔴 高' } as Record<string, string>)[p] || p

const statusLabel = (s: string) =>
  ({ pending: '⏳ 待办', completed: '✅ 完成', cancelled: '❌ 取消' } as Record<string, string>)[s] || s

const priorityClass = (p: string) => `priority-${p}`

const groupedEvents = computed(() => {
  const groups: Record<string, EventItem[]> = {}
  for (const e of events.value) {
    const t = e.start_time.slice(11, 16)
    if (!groups[t]) groups[t] = []
    groups[t].push(e)
  }
  return Object.entries(groups).sort(([a], [b]) => a.localeCompare(b))
})

async function loadEvents() {
  loading.value = true
  try {
    events.value = await fetchEvents(selectedDate.value)
  } catch {
    events.value = []
  } finally {
    loading.value = false
  }
}

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
    await loadEvents()
  } catch {}
}

onMounted(loadEvents)
</script>

<template>
  <div class="calendar-page">
    <div class="calendar-header">
      <h2>📅 日程</h2>
      <div class="header-actions">
        <input
          type="date"
          v-model="selectedDate"
          class="date-picker"
          @change="loadEvents"
        />
        <button class="btn-add" @click="showAddForm = !showAddForm">
          {{ showAddForm ? '取消' : '+ 添加日程' }}
        </button>
      </div>
    </div>

    <!-- Quick add form -->
    <div v-if="showAddForm" class="add-form">
      <div class="form-row">
        <input
          v-model="newTitle"
          class="form-input full"
          placeholder="标题（例如：部门周会）"
          @keyup.enter="handleAdd"
        />
      </div>
      <div class="form-row inline">
        <input v-model="newTime" type="time" class="form-input" />
        <span class="form-sep">→</span>
        <input v-model="newEndTime" type="time" class="form-input" placeholder="结束时间（可选）" />
        <select v-model="newPriority" class="form-input">
          <option value="low">🟢 低</option>
          <option value="normal">🟡 普通</option>
          <option value="high">🔴 高</option>
        </select>
      </div>
      <div class="form-row">
        <input v-model="newDesc" class="form-input full" placeholder="描述（可选）" />
      </div>
      <div v-if="addError" class="form-error">{{ addError }}</div>
      <button class="btn-primary" @click="handleAdd">确认添加</button>
    </div>

    <!-- Event list -->
    <div class="event-list" v-if="events.length > 0">
      <div
        v-for="[timeSlot, items] in groupedEvents"
        :key="timeSlot"
        class="time-group"
      >
        <div class="time-label">{{ timeSlot }}</div>
        <div
          v-for="event in items"
          :key="event.id"
          class="event-card"
          :class="priorityClass(event.priority)"
        >
          <div class="event-main">
            <div class="event-title">{{ event.title }}</div>
            <div class="event-meta">
              <span class="event-status">{{ statusLabel(event.status) }}</span>
              <span class="event-priority">{{ priorityLabel(event.priority) }}</span>
            </div>
            <div v-if="event.description" class="event-desc">{{ event.description }}</div>
          </div>
          <button
            class="event-delete"
            :title="delConfirmId === event.id ? '再次点击确认删除' : '删除'"
            @click="delConfirmId === event.id ? handleDelete(event.id) : (delConfirmId = event.id)"
          >
            {{ delConfirmId === event.id ? '确认删除？' : '🗑️' }}
          </button>
        </div>
      </div>
    </div>

    <div v-else-if="!loading" class="empty-state">
      <div class="empty-icon">📭</div>
      <p>{{ selectedDate }} 没有日程安排</p>
      <p class="empty-hint">可以在这个页面直接添加日程，或去对话页告诉 Agent</p>
    </div>
  </div>
</template>

<style scoped>
.calendar-page {
  padding: 24px 28px;
  height: 100vh;
  overflow-y: auto;
  background: #fff;
}

.calendar-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 20px;
}

.calendar-header h2 {
  margin: 0;
  font-size: 20px;
  font-weight: 600;
}

.header-actions {
  display: flex;
  gap: 12px;
  align-items: center;
}

.date-picker {
  padding: 8px 12px;
  border: 1px solid #e0e3e8;
  border-radius: 8px;
  font-size: 14px;
  font-family: inherit;
  outline: none;
}

.date-picker:focus {
  border-color: #6366f1;
}

.btn-add {
  padding: 8px 18px;
  background: #6366f1;
  color: #fff;
  border: none;
  border-radius: 8px;
  font-size: 14px;
  cursor: pointer;
  transition: background 0.15s;
}

.btn-add:hover {
  background: #4f46e5;
}

.add-form {
  background: #f8f9fc;
  border: 1px solid #e8ebf2;
  border-radius: 12px;
  padding: 16px;
  margin-bottom: 20px;
}

.form-row {
  margin-bottom: 10px;
}

.form-row.inline {
  display: flex;
  gap: 8px;
  align-items: center;
}

.form-input {
  padding: 8px 12px;
  border: 1px solid #dde0e6;
  border-radius: 6px;
  font-size: 14px;
  font-family: inherit;
  outline: none;
}

.form-input:focus {
  border-color: #6366f1;
}

.form-input.full {
  width: 100%;
  box-sizing: border-box;
}

.form-sep {
  color: #999;
  font-size: 14px;
}

.form-error {
  color: #ef4444;
  font-size: 13px;
  margin-bottom: 8px;
}

.btn-primary {
  padding: 8px 20px;
  background: #22c55e;
  color: #fff;
  border: none;
  border-radius: 8px;
  font-size: 14px;
  cursor: pointer;
}

.btn-primary:hover {
  background: #16a34a;
}

.event-list {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.time-group {
  /* no extra styling needed */
}

.time-label {
  font-size: 13px;
  font-weight: 600;
  color: #999;
  margin-bottom: 6px;
  padding-left: 4px;
}

.event-card {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  padding: 14px 16px;
  border-radius: 10px;
  background: #fafbfd;
  border: 1px solid #eef1f6;
  margin-bottom: 6px;
  transition: box-shadow 0.15s;
}

.event-card:hover {
  box-shadow: 0 2px 8px rgba(0,0,0,0.06);
}

.event-card.priority-high {
  border-left: 3px solid #ef4444;
}

.event-card.priority-normal {
  border-left: 3px solid #f59e0b;
}

.event-card.priority-low {
  border-left: 3px solid #63e29c;
}

.event-main {
  flex: 1;
}

.event-title {
  font-size: 15px;
  font-weight: 600;
  color: #1a1a2e;
  margin-bottom: 6px;
}

.event-meta {
  display: flex;
  gap: 12px;
  margin-bottom: 4px;
}

.event-status,
.event-priority {
  font-size: 12px;
  color: #888;
}

.event-desc {
  font-size: 13px;
  color: #999;
  margin-top: 4px;
}

.event-delete {
  background: none;
  border: none;
  cursor: pointer;
  padding: 4px 8px;
  border-radius: 6px;
  font-size: 13px;
  color: #999;
  flex-shrink: 0;
}

.event-delete:hover {
  background: #fef2f2;
  color: #ef4444;
}

.empty-state {
  text-align: center;
  padding: 60px 20px;
  color: #999;
}

.empty-icon {
  font-size: 48px;
  margin-bottom: 12px;
}

.empty-state p {
  margin: 4px 0;
  font-size: 15px;
}

.empty-hint {
  font-size: 13px !important;
  color: #bbb;
}
</style>
