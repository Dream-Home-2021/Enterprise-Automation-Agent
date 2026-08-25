<script setup lang="ts">
/**
 * 根组件 — 整体布局。
 *
 * 侧栏 + 主区 + 遮罩/Toast。挂载时自动调用 store.init()。
 */
import { onMounted } from 'vue'
import { useChatStore } from '@/stores/chat'
import AppSidebar from './components/AppSidebar.vue'
import ChatView from './components/ChatView.vue'
import LoadingOverlay from './components/LoadingOverlay.vue'
import Toast from './components/Toast.vue'

const store = useChatStore()

onMounted(() => {
  store.init()
})

function toggleSidebar() {
  store.toggleSidebar()
}
</script>

<template>
  <!-- Mobile hamburger -->
  <button id="mobile-menu-btn" @click="toggleSidebar" aria-label="菜单">
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
      <path d="M3 12h18M3 6h18M3 18h18"/>
    </svg>
  </button>

  <!-- Overlay backdrop when sidebar is open on mobile -->
  <Transition name="fade">
    <div
      v-if="store.sidebarOpen"
      class="sidebar-overlay"
      @click="store.closeSidebar"
    ></div>
  </Transition>

  <AppSidebar />
  <ChatView />

  <LoadingOverlay :visible="store.isLoading" />
  <Toast />
</template>

<style scoped>
#mobile-menu-btn {
  display: none;
  position: fixed;
  top: 12px;
  left: 12px;
  z-index: 50;
  background: var(--bubble);
  border: 1px solid rgba(255,255,255,0.08);
  border-radius: 10px;
  padding: 8px;
  cursor: pointer;
  color: var(--text);
  align-items: center;
  justify-content: center;
}
#mobile-menu-btn svg { width: 20px; height: 20px; }
.sidebar-overlay {
  display: none;
}

@media (max-width: 768px) {
  #mobile-menu-btn { display: flex !important; }
  .sidebar-overlay {
    display: block;
    position: fixed;
    inset: 0;
    background: rgba(0,0,0,0.4);
    z-index: 99;
  }
}
</style>