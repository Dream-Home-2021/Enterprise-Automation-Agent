/**
 * textarea 自动增高（与原 autoResize 一致）。
 */

import { ref, onMounted, onUnmounted, type Ref } from 'vue'

export function useAutoResize(textareaRef: Ref<HTMLTextAreaElement | null>) {
  const maxHeight = 200

  function resize() {
    const el = textareaRef.value
    if (!el) return
    el.style.height = 'auto'
    el.style.height = Math.min(el.scrollHeight, maxHeight) + 'px'
  }

  return { resize }
}