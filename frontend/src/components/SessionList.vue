<script setup lang="ts">
/**
 * 会话列表。
 */
import { useChatStore } from '@/stores/chat'
import SessionItem from './SessionItem.vue'

const store = useChatStore()
</script>

<template>
  <div class="session-list">
    <SessionItem
      v-for="s in store.sessions"
      :key="s.id"
      :session="s"
      :active="s.id === store.currentSessionId"
    />
  </div>
</template>

<style scoped>
.session-list {
  flex: 1;
  overflow-y: auto;
  padding: 0 8px;
}
</style>