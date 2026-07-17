import { createApp } from 'vue'
import { createRouter, createWebHistory } from 'vue-router'
import './style.css'
import App from './App.vue'
import ChatView from './views/ChatView.vue'
import CalendarView from './views/CalendarView.vue'
import SettingsView from './views/SettingsView.vue'
import MemoryView from './views/MemoryView.vue'
import { fetchSettings } from './api/client'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', name: 'chat', component: ChatView },
    { path: '/calendar', name: 'calendar', component: CalendarView },
    { path: '/settings', name: 'settings', component: SettingsView },
    { path: '/memory', name: 'memory', component: MemoryView },
  ],
})

let setupChecked = false
router.beforeEach(async (to) => {
  if (to.name === 'settings' || setupChecked) return true
  try {
    const current = await fetchSettings()
    setupChecked = true
    if (current.needs_setup) return { name: 'settings', query: { firstRun: '1' } }
  } catch {
    setupChecked = true
  }
  return true
})

const app = createApp(App)
app.use(router)
app.mount('#app')
