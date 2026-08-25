<script setup lang="ts">
/**
 * 错误横幅 — 显示在 input 上方。
 */
import { useChatStore } from '@/stores/chat'

const store = useChatStore()
</script>

<template>
  <Transition name="fade">
    <div v-if="store.error" class="error-banner">
      {{ store.error }}
    </div>
  </Transition>
</template>

<style scoped>
.error-banner {
  background: rgba(239,68,68,0.1);
  border: 1px solid rgba(239,68,68,0.2);
  color: #fca5a5;
  padding: 8px 14px;
  border-radius: 8px;
  font-size: 13px;
  margin: 0 auto 8px;
  max-width: 600px;
  text-align: center;
}
</style>