<script setup lang="ts">
/**
 * Toast 消息 — 固定在底部中央，自动消失。
 */
import { useChatStore } from '@/stores/chat'

const store = useChatStore()
</script>

<template>
  <Transition name="toast">
    <div v-if="store.toast" class="toast">{{ store.toast }}</div>
  </Transition>
</template>

<style scoped>
.toast {
  position: fixed;
  bottom: 100px;
  left: 50%;
  transform: translateX(-50%);
  background: var(--bubble);
  color: var(--text);
  padding: 8px 16px;
  border-radius: 8px;
  font-size: 13px;
  pointer-events: none;
  z-index: 999;
}
</style>