<script setup lang="ts">
import { useRouter, useRoute } from 'vue-router'
import NotificationToast from './components/NotificationToast.vue'
import { MessageSquare, CalendarDays } from '@lucide/vue'

const router = useRouter()
const route = useRoute()

const isActive = (name: string) => route.name === name
</script>

<template>
  <NotificationToast />
  <div class="app-layout">
    <!-- Sidebar -->
    <aside class="sidebar">
      <div class="sidebar-brand">
        <span class="brand-icon">
          <img src="/avatars/agent.png" alt="HyperAgent" class="brand-img" />
        </span>
        <span class="brand-text">HyperAgent</span>
      </div>

      <nav class="sidebar-nav">
        <button
          class="nav-item"
          :class="{ active: isActive('chat') }"
          @click="router.push('/')"
        >
          <span class="nav-icon"><MessageSquare :size="20" /></span>
          <span>对话</span>
        </button>
        <button
          class="nav-item"
          :class="{ active: isActive('calendar') }"
          @click="router.push('/calendar')"
        >
          <span class="nav-icon"><CalendarDays :size="20" /></span>
          <span>日程</span>
        </button>
      </nav>

      <div class="sidebar-footer">
        <div class="status-dot" title="DeepSeek V4 Flash"></div>
        <span class="status-text">DeepSeek V4 Flash</span>
      </div>
    </aside>

    <!-- Main content -->
    <main class="main-content">
      <router-view />
    </main>
  </div>
</template>

<style scoped>
.app-layout {
  display: flex;
  height: 100vh;
  background: #f5f6fa;
}

.sidebar {
  width: 220px;
  background: #1a1a2e;
  color: #eee;
  display: flex;
  flex-direction: column;
  flex-shrink: 0;
}

.sidebar-brand {
  padding: 24px 20px 20px;
  display: flex;
  align-items: center;
  gap: 10px;
  border-bottom: 1px solid rgba(255,255,255,0.08);
}

.brand-icon {
  font-size: 28px;
  width: 32px;
  height: 32px;
  display: flex;
  align-items: center;
  justify-content: center;
}

.brand-img {
  width: 100%;
  height: 100%;
  object-fit: contain;
}

.brand-text {
  font-size: 18px;
  font-weight: 700;
  letter-spacing: 0.5px;
}

.sidebar-nav {
  padding: 16px 12px;
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.nav-item {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 12px 16px;
  border: none;
  border-radius: 8px;
  background: transparent;
  color: #aaa;
  font-size: 15px;
  cursor: pointer;
  transition: all 0.15s;
  text-align: left;
  width: 100%;
}

.nav-item:hover {
  background: rgba(255,255,255,0.08);
  color: #eee;
}

.nav-item.active {
  background: rgba(99, 102, 241, 0.25);
  color: #a5b4fc;
}

.nav-icon {
  font-size: 18px;
  width: 24px;
  text-align: center;
}

.sidebar-footer {
  padding: 16px 20px;
  border-top: 1px solid rgba(255,255,255,0.08);
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 12px;
  color: #888;
}

.status-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: #22c55e;
}

.main-content {
  flex: 1;
  overflow: hidden;
}
</style>
