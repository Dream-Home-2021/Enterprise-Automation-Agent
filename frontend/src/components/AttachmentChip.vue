<script setup lang="ts">
/**
 * 附件标签 — 文件名 + 大小 + 移除按钮。
 */
import { useChatStore } from '@/stores/chat'

const store = useChatStore()

function formatSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}

function remove() {
  store.setAttachment(null)
}
</script>

<template>
  <Transition name="chip">
    <div v-if="store.pendingAttachment" class="chip">
      <span class="chip-icon">📎</span>
      <span class="chip-name">{{ store.pendingAttachment.name }}</span>
      <span class="chip-size">{{ formatSize(store.pendingAttachment.size) }}</span>
      <button class="chip-remove" @click="remove" title="移除附件">✕</button>
    </div>
  </Transition>
</template>

<style scoped>
.chip {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  background: rgba(99,102,241,0.12);
  border: 1px solid rgba(99,102,241,0.25);
  border-radius: 8px;
  padding: 4px 10px;
  font-size: 12px;
  color: var(--text);
  max-width: 100%;
}
.chip-icon { flex-shrink: 0; font-size: 13px; }
.chip-name {
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  max-width: 180px;
}
.chip-size { color: var(--text-dim); flex-shrink: 0; font-size: 11px; }
.chip-remove {
  background: none;
  border: none;
  color: var(--text-dim);
  cursor: pointer;
  font-size: 12px;
  padding: 1px 2px;
  line-height: 1;
  border-radius: 4px;
  transition: color 0.1s, background 0.1s;
  flex-shrink: 0;
}
.chip-remove:hover {
  color: #ef4444;
  background: rgba(239,68,68,0.1);
}
</style>