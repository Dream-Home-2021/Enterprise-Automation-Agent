<script setup lang="ts">
/**
 * 消息气泡 — 用户消息（紫色底，右对齐） / AI 消息（透明底，左对齐 + 头像 + 复制）。
 *
 * 头像从 /images/*.png 加载，加载失败以 emoji 兜底。
 * AI 消息尾条可能带流式 delta 动画。
 */
import { ref, computed, nextTick } from 'vue'
import { useChatStore } from '@/stores/chat'

const props = defineProps<{
  message: { role: string; content: string }
  isLastStreaming?: boolean
}>()

const aiAvatar = '/images/ai.png'
const userAvatar = '/images/user.png'
const store = useChatStore()
const isUser = computed(() => props.message.role === 'user')

async function copy() {
  try {
    await navigator.clipboard.writeText(props.message.content)
    store.showToast('已复制')
  } catch {
    // fallback
    const ta = document.createElement('textarea')
    ta.value = props.message.content
    document.body.appendChild(ta)
    ta.select()
    document.execCommand('copy')
    ta.remove()
    store.showToast('已复制')
  }
}
</script>

<template>
  <div class="message-row" :class="isUser ? 'user-row' : 'ai-row'">
    <!-- AI avatar (left) -->
    <div v-if="!isUser" class="avatar">
      <img :src="aiAvatar" alt="AI" @error="($event.target as HTMLElement).outerHTML='🤖'">
    </div>

    <div class="content" :class="{ 'stream-delta': isLastStreaming }">
      {{ message.content }}
      <!-- Actions: only for AI messages -->
      <div v-if="!isUser && !isLastStreaming" class="message-actions">
        <button @click="copy">复制</button>
      </div>
    </div>

    <!-- User avatar (right) -->
    <div v-if="isUser" class="avatar user-avatar">
      <img :src="userAvatar" alt="User" @error="($event.target as HTMLElement).outerHTML='👤'">
    </div>
  </div>
</template>

<style scoped>
.message-row {
  padding: 16px 0;
  display: flex;
  gap: 12px;
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
  font-size: 14px;
  overflow: hidden;
}
.avatar img { width: 100%; height: 100%; object-fit: cover; }
.avatar.user-avatar { background: var(--purple); }

.content {
  flex: 1;
  min-width: 0;
  line-height: 1.7;
  font-size: 15px;
  color: var(--text);
  white-space: pre-wrap;
  word-wrap: break-word;
}

/* User message: purple bubble, right-aligned */
.user-row .content {
  background: var(--bubble);
  padding: 12px 16px;
  border-radius: 16px 16px 4px 16px;
  max-width: 70%;
  margin-left: auto;
}
.user-row { justify-content: flex-end; }
.user-row .avatar { order: 1; margin-left: 0; }

/* AI message actions */
.message-actions {
  display: none;
  margin-top: 8px;
  gap: 6px;
}
.ai-row:hover .message-actions { display: flex; }
.message-actions button {
  background: transparent;
  border: none;
  color: #666;
  cursor: pointer;
  font-size: 12px;
  padding: 2px 6px;
  border-radius: 4px;
  transition: all 0.1s;
}
.message-actions button:hover {
  background: rgba(255,255,255,0.06);
  color: #999;
}

/* Stream delta animation */
.stream-delta {
  animation: text-pop 0.15s ease-out;
}

@media (max-width: 768px) {
  .message-row { padding-left: 12px; padding-right: 12px; }
  .content { font-size: 14px; }
}
</style>