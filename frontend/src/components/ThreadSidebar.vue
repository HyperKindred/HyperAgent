<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import {
  chatStore,
  loadThreadList,
  switchThread,
  clearChat,
  deleteThreadById,
  renameThreadById,
} from '../store/chat'

const route = useRoute()
const renaming = ref<string | null>(null)
const renameInput = ref('')
const confirmingDelete = ref<string | null>(null)

onMounted(async () => {
  await loadThreadList()
})

function formatTime(iso: string): string {
  const d = new Date(iso)
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
</script>

<template>
  <div class="thread-sidebar">
    <div class="sidebar-header">
      <div class="brand">
        <span class="brand-icon">🤖</span>
        <span class="brand-name">HyperAgent</span>
      </div>
      <button class="new-chat-btn" @click="handleNewChat" title="新对话">
        + 新对话
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
              >✏️</button>
              <button
                class="action-btn delete-btn"
                title="删除"
                @click="(e) => handleDelete(e, thread.id)"
              >🗑️</button>
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

    <div class="sidebar-footer">
      <router-link
        to="/"
        class="nav-item"
        :class="{ active: route.name === 'chat' }"
      >
        <span>💬</span> 对话
      </router-link>
      <router-link
        to="/calendar"
        class="nav-item"
        :class="{ active: route.name === 'calendar' }"
      >
        <span>📅</span> 日程
      </router-link>
    </div>
  </div>
</template>

<style scoped>
.thread-sidebar {
  width: 240px;
  height: 100vh;
  background: #1a1a2e;
  color: #e0e0e0;
  display: flex;
  flex-direction: column;
  flex-shrink: 0;
  overflow: hidden;
}

.sidebar-header {
  padding: 16px;
  border-bottom: 1px solid rgba(255, 255, 255, 0.08);
}

.brand {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 12px;
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
}

.new-chat-btn:hover {
  background: rgba(255, 255, 255, 0.06);
  color: #fff;
  border-color: rgba(255, 255, 255, 0.4);
}

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

.sidebar-footer {
  padding: 12px 16px;
  border-top: 1px solid rgba(255, 255, 255, 0.08);
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.nav-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 12px;
  border-radius: 8px;
  font-size: 13px;
  color: #808098;
  text-decoration: none;
  transition: all 0.15s;
}

.nav-item:hover {
  background: rgba(255, 255, 255, 0.06);
  color: #e0e0e0;
}

.nav-item.active {
  background: rgba(99, 102, 241, 0.15);
  color: #6366f1;
}
</style>
