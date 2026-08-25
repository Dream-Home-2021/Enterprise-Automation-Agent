<script setup lang="ts">
/**
 * 会话列表项 — 悬停显示 ✕ 删除。
 */
import { useChatStore } from '@/stores/chat'
import type { Session } from '@/types'

const props = defineProps<{ session: Session; active: boolean }>()
const store = useChatStore()

function onClick() {
  store.switchSession(props.session.id)
}

function onDelete(e: MouseEvent) {
  e.stopPropagation()
  if (!confirm('确定要删除这个会话吗？')) return
  store.deleteSession(props.session.id)
}
</script>

<template>
  <div
    class="session-item"
    :class="{ active }"
    @click="onClick"
  >
    <span class="icon">📝</span>
    <span class="name">{{ session.name || '新会话' }}</span>
    <button class="del-btn" @click="onDelete" title="删除会话">✕</button>
  </div>
</template>

<style scoped>
.session-item {
  display: flex;
  align-items: center;
  padding: 10px 12px;
  border-radius: 8px;
  cursor: pointer;
  transition: background 0.12s;
  margin: 1px 0;
  position: relative;
  gap: 8px;
}
.session-item:hover { background: rgba(255,255,255,0.06); }
.session-item.active {
  background: rgba(99,102,241,0.12);
  color: #e0e0ff;
}
.icon { font-size: 14px; flex-shrink: 0; }
.name {
  flex: 1;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  font-size: 13px;
}
.del-btn {
  opacity: 0;
  width: 24px;
  height: 24px;
  border: none;
  background: transparent;
  color: #888;
  cursor: pointer;
  border-radius: 6px;
  font-size: 14px;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  transition: all 0.12s;
}
.session-item:hover .del-btn { opacity: 0.6; }
.del-btn:hover { opacity: 1 !important; background: rgba(255,255,255,0.08); color: #ef4444; }
</style>