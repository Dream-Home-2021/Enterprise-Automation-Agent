<script setup lang="ts">
/**
 * 欢迎屏 — 无消息时显示，带 fade transition。
 */
import { useChatStore } from '@/stores/chat'

const store = useChatStore()
</script>

<template>
  <Transition name="fade">
    <div v-if="!store.hasMessages" class="welcome">
      <div class="logo">🤖</div>
      <h1>有什么可以帮助你的？</h1>
      <p>在下方输入你的问题，我可以帮你解答、分析、写作、编程等。</p>
    </div>
  </Transition>
</template>

<style scoped>
.welcome {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  height: 100%;
  padding: 40px 20px;
  text-align: center;
}
.logo { font-size: 48px; margin-bottom: 16px; }
h1 { font-size: 24px; font-weight: 600; margin-bottom: 8px; color: var(--text); }
p { color: var(--text-dim); font-size: 14px; max-width: 400px; line-height: 1.6; }
</style>