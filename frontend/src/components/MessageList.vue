<script setup lang="ts">
/**
 * 消息列表 — 使用 TransitionGroup 实现消息进出动效。
 */
import { useChatStore } from '@/stores/chat'
import MessageBubble from './MessageBubble.vue'

const store = useChatStore()
</script>

<template>
  <TransitionGroup name="msg" tag="div" class="msg-container">
    <MessageBubble
      v-for="(msg, idx) in store.messages"
      :key="`msg-${idx}`"
      :message="msg"
      :is-last-streaming="idx === store.messages.length - 1 && store.isStreaming"
    />
  </TransitionGroup>
</template>

<style scoped>
.msg-container {
  width: 100%;
}
</style>