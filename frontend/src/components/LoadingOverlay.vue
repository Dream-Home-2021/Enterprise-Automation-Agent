<script setup lang="ts">
/**
 * 加载遮罩 — 覆盖全屏的 spinner。
 */
defineProps<{ visible: boolean }>()
</script>

<template>
  <Transition name="fade">
    <div v-if="visible" class="overlay">
      <div class="spinner"></div>
    </div>
  </Transition>
</template>

<style scoped>
.overlay {
  position: fixed;
  inset: 0;
  background: rgba(0,0,0,0.6);
  z-index: 1000;
  display: flex;
  align-items: center;
  justify-content: center;
}
.spinner {
  width: 40px;
  height: 40px;
  border: 3px solid rgba(255,255,255,0.1);
  border-top-color: var(--purple);
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
}
</style>