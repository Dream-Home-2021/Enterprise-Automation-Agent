<script setup lang="ts">
/**
 * 输入提示 — 三点跳动渐变显隐。
 */
const aiAvatar = '/images/ai.png'
defineProps<{ visible: boolean }>()
</script>

<template>
  <Transition name="fade">
    <div v-if="visible" class="typing-row">
      <div class="avatar">
        <img :src="aiAvatar" alt="AI" @error="($event.target as HTMLElement).outerHTML='🤖'">
      </div>
      <div class="dots">
        <span class="dot"></span>
        <span class="dot"></span>
        <span class="dot"></span>
      </div>
    </div>
  </Transition>
</template>

<style scoped>
.typing-row {
  display: flex;
  gap: 12px;
  padding: 16px 0;
  max-width: var(--maxw);
  margin: 0 auto;
  width: 100%;
  padding-left: 24px;
  padding-right: 24px;
}
.avatar {
  width: 32px;
  height: 32px;
  border-radius: 50%;
  flex-shrink: 0;
  background: var(--bubble);
  display: flex;
  align-items: center;
  justify-content: center;
  overflow: hidden;
}
.avatar img { width: 100%; height: 100%; object-fit: cover; }
.dots { display: flex; gap: 4px; align-items: center; padding: 8px 0; }
.dot {
  width: 8px; height: 8px;
  border-radius: 50%;
  background: var(--purple);
  animation: bounce 1.4s infinite ease-in-out;
}
.dot:nth-child(2) { animation-delay: 0.16s; }
.dot:nth-child(3) { animation-delay: 0.32s; }
</style>