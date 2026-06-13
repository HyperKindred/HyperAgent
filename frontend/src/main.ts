import { createApp } from 'vue'
import { createRouter, createWebHistory } from 'vue-router'
import './style.css'
import App from './App.vue'
import ChatView from './views/ChatView.vue'
import CalendarView from './views/CalendarView.vue'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', name: 'chat', component: ChatView },
    { path: '/calendar', name: 'calendar', component: CalendarView },
  ],
})

const app = createApp(App)
app.use(router)
app.mount('#app')
