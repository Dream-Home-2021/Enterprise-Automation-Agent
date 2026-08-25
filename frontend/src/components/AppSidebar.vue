<script setup lang="ts">
/**
 * 侧边栏 — 会话管理区域。
 */
import { useChatStore } from '@/stores/chat'
import SessionList from './SessionList.vue'

const store = useChatStore()

function newSession() {
  store.createSession()
}
</script>

<template>
  <aside id="sidebar" :class="{ active: store.sidebarOpen }">
    <div id="sidebar-header">💬 会话</div>
    <button id="new-chat-btn" @click="newSession">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
        <path d="M12 5v14M5 12h14"/>
      </svg>
      新会话
    </button>
    <SessionList />
    <div id="sidebar-footer">
      <small style="color:#555;font-size:11px;padding:0 4px;">My Agent</small>
    </div>
  </aside>
</template>

<style scoped>
#sidebar {
  width: 260px;
  min-width: 260px;
  background: var(--bg-sidebar);
  display: flex;
  flex-direction: column;
  border-right: 1px solid rgba(255,255,255,0.06);
  height: 100vh;
}
#sidebar-header {
  padding: 16px 14px 8px;
  font-size: 13px;
  color: var(--text-dim);
  font-weight: 600;
  letter-spacing: 0.5px;
}
#new-chat-btn {
  margin: 4px 10px 10px;
  padding: 10px 14px;
  background: transparent;
  color: var(--text);
  border: 1px solid rgba(255,255,255,0.12);
  border-radius: 10px;
  cursor: pointer;
  font-size: 13px;
  display: flex;
  align-items: center;
  gap: 8px;
  transition: background 0.15s;
}
#new-chat-btn:hover { background: rgba(255,255,255,0.06); }
#new-chat-btn svg { width: 16px; height: 16px; opacity: 0.7; }
#sidebar-footer {
  padding: 10px;
  border-top: 1px solid rgba(255,255,255,0.06);
}

@media (max-width: 768px) {
  #sidebar { display: none; }
  #sidebar.active { display: flex; position: fixed; z-index: 100; width: 280px; }
}
</style>