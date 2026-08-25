<script setup lang="ts">
/**
 * 发送按钮。
 */
defineProps<{ disabled: boolean }>()
</script>

<template>
  <button
    class="send-btn"
    :disabled="disabled"
    aria-label="发送"
    type="button"
  >
    <svg viewBox="0 0 24 24" fill="currentColor">
      <path d="M2.01 21L23 12 2.01 3 2 10l15 2-15 2z"/>
    </svg>
  </button>
</template>

<style scoped>
.send-btn {
  width: 36px;
  height: 36px;
  border-radius: 50%;
  border: none;
  background: var(--purple);
  color: white;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  transition: background 0.15s, transform 0.15s;
}
.send-btn:hover:not(:disabled) {
  background: var(--purple-hover);
  transform: scale(1.05);
}
.send-btn:active:not(:disabled) {
  transform: scale(0.95);
}
.send-btn:disabled {
  background: #333;
  cursor: not-allowed;
  opacity: 0.5;
}
.send-btn svg { width: 18px; height: 18px; }
</style>