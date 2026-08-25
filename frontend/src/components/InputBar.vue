<script setup lang="ts">
/**
 * 输入栏 — 包含回形针按钮 + 附件标签 + textarea + 发送按钮。
 *
 * textarea 自动增高；Enter 发送（Shift+Enter 换行）。
 * 发送时拼装附件内容为代码块，附带 attachments 元数据字段（后端 pydantic 忽略）。
 */
import { ref } from 'vue'
import { useChatStore } from '@/stores/chat'
import { useChatStream } from '@/composables/useChatStream'
import { useAutoResize } from '@/composables/useAutoResize'
import UploadButton from './UploadButton.vue'
import AttachmentChip from './AttachmentChip.vue'
import SendButton from './SendButton.vue'
import ErrorBanner from './ErrorBanner.vue'
import type { SSEEvent } from '@/types'

const store = useChatStore()
const stream = useChatStream()
const textareaRef = ref<HTMLTextAreaElement | null>(null)
const textareaValue = ref('')
const { resize } = useAutoResize(textareaRef)

function focusInput() {
  setTimeout(() => textareaRef.value?.focus(), 0)
}

async function handleSend() {
  const text = textareaValue.value.trim()
  if (!text || store.isStreaming || !store.currentSessionId) return

  // Reset input
  textareaValue.value = ''
  resize()
  store.clearError()

  // Build message with optional attachment
  let message = text
  const att = store.pendingAttachment
  if (att?.content) {
    message += `\n\n[附件: ${att.name}]\n\`\`\`\n${att.content}\n\`\`\``
  }

  const payload: Record<string, unknown> = {
    message,
    session_id: store.currentSessionId,
    user_id: 1,
    history: store.historyForApi,
    attachments: att
      ? [{ name: att.name, size: att.size, type: att.type }]
      : [],
  }

  // Clear attachment
  store.setAttachment(null)

  // Add user message
  store.addMessage({ role: 'user', content: message })

  // Add placeholder for AI response
  store.addMessage({ role: 'assistant', content: '' })
  store.isStreaming = true

  await stream.send(payload, (evt) => {
    switch (evt.type) {
      case 'chunk':
        store.appendToLastAssistant(evt.content)
        break
      case 'title':
        if (evt.sessions) {
          store.sessions = evt.sessions
        }
        break
      case 'human_choice':
        store.setPendingHumanAction({
          actionId: evt.action_id,
          type: 'choice',
          options: evt.options,
        })
        store.isStreaming = false
        break
      case 'human_review':
        store.setPendingHumanAction({
          actionId: evt.action_id,
          type: 'review',
          options: evt.options,
          prompt: evt.prompt,
        })
        store.isStreaming = false
        break
      case 'done':
        store.isStreaming = false
        break
      case 'error':
        store.setError(evt.message || '服务器错误')
        store.isStreaming = false
        break
    }
  })

  if (store.isStreaming) store.isStreaming = false
  focusInput()
}

function onKeydown(e: KeyboardEvent) {
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault()
    handleSend()
  }
}
</script>

<template>
  <div class="input-area">
    <ErrorBanner />
    <div class="input-wrapper">
      <!-- File upload (left) -->
      <UploadButton />

      <!-- Input inner: attachment chip + textarea -->
      <div class="input-inner">
        <AttachmentChip />
        <div class="textarea-row">
          <textarea
            ref="textareaRef"
            v-model="textareaValue"
            class="message-input"
            rows="1"
            placeholder="输入消息..."
            @keydown="onKeydown"
            @input="resize"
            :disabled="store.isStreaming"
          ></textarea>
        </div>
      </div>

      <!-- Send button (right) -->
      <SendButton
        :disabled="store.isStreaming || !store.currentSessionId"
        @click="handleSend"
      />
    </div>
  </div>
</template>

<style scoped>
.input-area {
  padding: 16px 24px 24px;
  max-width: var(--maxw);
  margin: 0 auto;
  width: 100%;
}
.input-wrapper {
  display: flex;
  align-items: flex-end;
  gap: 8px;
  background: var(--bubble);
  border: 1px solid rgba(255,255,255,0.08);
  border-radius: 16px;
  padding: 8px 8px 8px 8px;
  transition: border-color 0.2s;
}
.input-wrapper:focus-within {
  border-color: rgba(99,102,241,0.4);
}
.input-inner {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 4px;
  min-width: 0;
}
.textarea-row {
  display: flex;
  align-items: flex-end;
}
.message-input {
  flex: 1;
  border: none;
  background: transparent;
  color: var(--text);
  font-size: 15px;
  font-family: inherit;
  line-height: 1.5;
  resize: none;
  outline: none;
  max-height: 200px;
  min-height: 24px;
}
.message-input::placeholder { color: #666; }
.message-input:disabled { opacity: 0.5; }

@media (max-width: 768px) {
  .input-area { padding: 12px 12px 16px; }
}
</style>