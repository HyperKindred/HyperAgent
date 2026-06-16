<script setup lang="ts">
import NotificationToast from './components/NotificationToast.vue'
import ThreadSidebar from './components/ThreadSidebar.vue'
</script>

<template>
  <NotificationToast />
  <div class="app-layout">
    <ThreadSidebar />
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

.main-content {
  flex: 1;
  overflow: hidden;
}
</style>
