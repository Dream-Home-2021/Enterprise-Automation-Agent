<script setup lang="ts">
/**
 * 人工选择对话框 — 在聊天区上方弹出选择按钮。
 *
 * 用于 human_choice_node（2个选项并排）和 human_review_node（yes/no + 可选输入框）。
 */
import { ref } from 'vue'

const props = defineProps<{
  options: string[]
  actionId: string
  type: 'choice' | 'review'
  prompt?: string
}>()

const emit = defineEmits<{
  confirm: [choice: string, inputText: string]
  cancel: []
}>()

const inputText = ref('')
const showInput = ref(props.type === 'review')

function handleConfirm(choice: string) {
  if (showInput.value && !inputText.value.trim() && choice === 'yes') {
    return // 要求输入内容
  }
  emit('confirm', choice, inputText.value)
}

function handleCancel() {
  emit('cancel')
}
</script>

<template>
  <div class="human-dialog-overlay">
    <div class="human-dialog">
      <div v-if="prompt" class="dialog-prompt">{{ prompt }}</div>

      <!-- Choice buttons side by side -->
      <div class="dialog-options">
        <button
          v-for="opt in options"
          :key="opt"
          class="dialog-btn"
          :class="{ 'btn-primary': opt === 'yes' || opt === '继续研究过程' }"
          @click="handleConfirm(opt)"
        >
          {{ opt }}
        </button>
      </div>

      <!-- Optional input textarea (for review yes or choice area input) -->
      <div v-if="showInput" class="dialog-input-area">
        <textarea
          v-model="inputText"
          class="dialog-input"
          rows="2"
          :placeholder="type === 'review' ? '请输入您的修改请求...' : '指定要修改的区域（可选）'"
        ></textarea>
      </div>

      <button class="dialog-cancel" @click="handleCancel">取消</button>
    </div>
  </div>
</template>

<style scoped>
.human-dialog-overlay {
  position: relative;
  width: 100%;
  max-width: var(--maxw);
  margin: 0 auto;
  padding: 0 24px;
  z-index: 10;
}

.human-dialog {
  background: linear-gradient(135deg, #1e1b4b 0%, #0f0a2e 100%);
  border: 1px solid rgba(139, 92, 246, 0.3);
  border-radius: 16px;
  padding: 20px 24px;
  box-shadow: 0 8px 32px rgba(0, 0, 0, 0.4), 0 0 0 1px rgba(139, 92, 246, 0.15);
}

.dialog-prompt {
  color: #e0d9ff;
  font-size: 14px;
  margin-bottom: 16px;
  line-height: 1.5;
}

.dialog-options {
  display: flex;
  gap: 12px;
  flex-wrap: wrap;
}

.dialog-btn {
  flex: 1;
  min-width: 120px;
  padding: 12px 20px;
  border: 1px solid rgba(255, 255, 255, 0.12);
  border-radius: 12px;
  background: rgba(255, 255, 255, 0.06);
  color: #e0d9ff;
  font-size: 15px;
  cursor: pointer;
  transition: all 0.2s ease;
  text-align: center;
}

.dialog-btn:hover {
  background: rgba(139, 92, 246, 0.2);
  border-color: rgba(139, 92, 246, 0.5);
  transform: translateY(-1px);
}

.dialog-btn.btn-primary {
  background: rgba(139, 92, 246, 0.25);
  border-color: rgba(139, 92, 246, 0.4);
  font-weight: 600;
}

.dialog-btn.btn-primary:hover {
  background: rgba(139, 92, 246, 0.4);
  border-color: rgba(139, 92, 246, 0.7);
}

.dialog-input-area {
  margin-top: 16px;
}

.dialog-input {
  width: 100%;
  border: 1px solid rgba(255, 255, 255, 0.12);
  background: rgba(0, 0, 0, 0.3);
  color: #e0d9ff;
  border-radius: 10px;
  padding: 10px 14px;
  font-size: 14px;
  font-family: inherit;
  resize: none;
  outline: none;
  transition: border-color 0.2s;
  box-sizing: border-box;
}

.dialog-input:focus {
  border-color: rgba(139, 92, 246, 0.5);
}

.dialog-input::placeholder {
  color: rgba(255, 255, 255, 0.35);
}

.dialog-cancel {
  display: none;
}

@media (max-width: 768px) {
  .human-dialog-overlay {
    padding: 0 12px;
  }
  .dialog-options {
    flex-direction: column;
  }
  .dialog-btn {
    min-width: unset;
  }
}
</style>