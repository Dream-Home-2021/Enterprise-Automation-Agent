/**
 * Toast 状态管理。
 * 实际 toast 显示由 store.showToast 驱动，此处仅保留类型。
 *
 * 使用方式：
 *   const store = useChatStore()
 *   store.showToast('已复制')
 */

export { useChatStore } from '@/stores/chat'