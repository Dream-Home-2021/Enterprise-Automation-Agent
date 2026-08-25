<script setup lang="ts">
/**
 * 会话主视图 — 消息区、人工选择对话框、输入区。
 * 自动滚动到底部（新消息 / 流式增量）。
 */
import { ref, watch, nextTick } from 'vue'
import { useChatStore } from '@/stores/chat'
import { useChatStream } from '@/composables/useChatStream'
import WelcomeScreen from './WelcomeScreen.vue'
import MessageList from './MessageList.vue'
import TypingIndicator from './TypingIndicator.vue'
import InputBar from './InputBar.vue'
import HumanChoiceDialog from './HumanChoiceDialog.vue'

const store = useChatStore()
const stream = useChatStream()
const messagesRef = ref<HTMLElement | null>(null)

/** 有新消息或流式增量时自动滚动到底部。 */
function scrollToBottom() {
  nextTick(() => {
    if (messagesRef.value) {
      messagesRef.value.scrollTop = messagesRef.value.scrollHeight
    }
  })
}

// 监听 messages 变化自动滚动
watch(
  () => store.messages.length,
  () => scrollToBottom(),
)

// 监听流式增量（最后一条 content 变化）
watch(
  () => store.messages[store.messages.length - 1]?.content,
  () => {
    if (store.isStreaming) scrollToBottom()
  },
)

/** 用户在 HumanChoiceDialog 中做出选择后的回调 */
async function handleHumanChoice(choice: string, inputText: string) {
  const action = store.pendingHumanAction
  if (!action || !store.currentSessionId) return

  const actionId = action.actionId
  store.clearPendingHumanAction()

  // 将用户选择添加到消息列表
  const choiceMsg = inputText
    ? `[选择: ${choice}] ${inputText}`
    : `[选择: ${choice}]`
  store.addMessage({ role: 'user', content: choiceMsg })

  // 添加占位 AI 消息
  store.addMessage({ role: 'assistant', content: '' })
  store.isStreaming = true

  await stream.resume(store.currentSessionId, actionId, choice, inputText, (evt) => {
    switch (evt.type) {
      case 'chunk':
        store.appendToLastAssistant(evt.content)
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
}
</script>

<template>
  <div class="chat-view">
    <!-- Messages area -->
    <div ref="messagesRef" class="messages">
      <WelcomeScreen />
      <div class="message-scroll">
        <MessageList />
        <TypingIndicator
          :visible="
            store.isStreaming &&
            (store.messages.length === 0 ||
              store.messages[store.messages.length - 1]?.content === '')
          "
        />
      </div>
    </div>

    <!-- Human choice dialog (between messages and input) -->
    <HumanChoiceDialog
      v-if="store.pendingHumanAction"
      :options="store.pendingHumanAction.options"
      :action-id="store.pendingHumanAction.actionId"
      :type="store.pendingHumanAction.type"
      :prompt="store.pendingHumanAction.prompt"
      @confirm="handleHumanChoice"
    />

    <!-- Input area -->
    <InputBar />
  </div>
</template>

<style scoped>
.chat-view {
  flex: 1;
  display: flex;
  flex-direction: column;
  height: 100vh;
  min-width: 0;
}
.messages {
  flex: 1;
  overflow-y: auto;
  scroll-behavior: smooth;
  display: flex;
  flex-direction: column;
}
.message-scroll {
  flex: 1;
}
</style>