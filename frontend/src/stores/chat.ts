/**
 * Chat Store — 单一数据源。
 *
 * 状态: sessions, currentSessionId, messages, isStreaming, isLoading, error,
 *       pendingAttachment, sidebarOpen
 *
 * messages 替代原 DOM 反读（getCurrentHistory），派生 historyForApi 供 SSE 请求体使用。
 */

import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { api } from '@/api/client'
import type { Session, Message, Attachment } from '@/types'

export type HumanActionType = 'choice' | 'review'

export interface PendingHumanAction {
  actionId: string
  type: HumanActionType
  options: string[]
  prompt?: string
}

export const useChatStore = defineStore('chat', () => {
  /* ── State ─────────────────────────────────────────────────────── */
  const sessions = ref<Session[]>([])
  const currentSessionId = ref<string | null>(null)
  const messages = ref<Message[]>([])
  const isStreaming = ref(false)
  const isLoading = ref(false)
  const error = ref('')
  const pendingAttachment = ref<Attachment | null>(null)
  const sidebarOpen = ref(false)
  const pendingHumanAction = ref<PendingHumanAction | null>(null)

  let _toastTimer: ReturnType<typeof setTimeout> | null = null
  const toast = ref('')

  /* ── Getters ───────────────────────────────────────────────────── */
  const currentSession = computed(() =>
    sessions.value.find(s => s.id === currentSessionId.value) ?? null,
  )

  const hasMessages = computed(() => messages.value.length > 0)

  /** 映射成后端 API 所需的 {role, content}[] 格式（DOM 反读替代）。 */
  const historyForApi = computed(() =>
    messages.value.map(m => ({ role: m.role, content: m.content })),
  )

  /* ── Actions ───────────────────────────────────────────────────── */

  /** 应用初始化：加载会话列表 + 历史。 */
  async function init() {
    isLoading.value = true
    error.value = ''
    try {
      const data = await api.init()
      sessions.value = data.sessions
      currentSessionId.value = data.current_session_id
      messages.value = data.history ?? []
    } catch (e: any) {
      error.value = `加载失败: ${e.message}`
    } finally {
      isLoading.value = false
    }
  }

  /** 创建新会话。 */
  async function createSession() {
    isLoading.value = true
    error.value = ''
    try {
      const data = await api.createSession()
      sessions.value = data.sessions
      currentSessionId.value = data.session_id
      messages.value = []
    } catch (e: any) {
      error.value = `创建会话失败: ${e.message}`
    } finally {
      isLoading.value = false
    }
  }

  /** 切换会话。 */
  async function switchSession(id: string) {
    if (id === currentSessionId.value) return
    currentSessionId.value = id
    pendingAttachment.value = null // 切换会话清空附件
    messages.value = []
    isLoading.value = true
    error.value = ''
    try {
      const data = await api.getHistory(id)
      messages.value = data.history ?? []
    } catch (e: any) {
      error.value = `加载历史失败: ${e.message}`
    } finally {
      isLoading.value = false
    }
  }

  /** 删除会话。 */
  async function deleteSession(id: string) {
    isLoading.value = true
    error.value = ''
    try {
      const data = await api.deleteSession(id)
      sessions.value = data.sessions
      currentSessionId.value = data.session_id
      messages.value = data.history ?? []
    } catch (e: any) {
      error.value = `删除失败: ${e.message}`
    } finally {
      isLoading.value = false
    }
  }

  /** 添加一条消息。 */
  function addMessage(msg: Message) {
    messages.value.push(msg)
  }

  /** 追加到最后一条 AI 消息（流式 delta）。 */
  function appendToLastAssistant(delta: string) {
    const last = messages.value[messages.value.length - 1]
    if (last && last.role === 'assistant') {
      last.content += delta
    } else {
      // 安全兜底：如果没有 AI 消息，新建一条
      messages.value.push({ role: 'assistant', content: delta })
    }
  }

  /** 清空消息。 */
  function clearMessages() {
    messages.value = []
  }

  function setError(msg: string) {
    error.value = msg
  }

  function clearError() {
    error.value = ''
  }

  function setAttachment(a: Attachment | null) {
    pendingAttachment.value = a
  }

  function toggleSidebar() {
    sidebarOpen.value = !sidebarOpen.value
  }

  function closeSidebar() {
    sidebarOpen.value = false
  }

  function showToast(text: string, duration = 2000) {
    toast.value = text
    if (_toastTimer) clearTimeout(_toastTimer)
    _toastTimer = setTimeout(() => {
      toast.value = ''
    }, duration)
  }

  function setPendingHumanAction(action: PendingHumanAction | null) {
    pendingHumanAction.value = action
  }

  function clearPendingHumanAction() {
    pendingHumanAction.value = null
  }

  return {
    // state
    sessions,
    currentSessionId,
    messages,
    isStreaming,
    isLoading,
    error,
    pendingAttachment,
    sidebarOpen,
    toast,
    pendingHumanAction,
    // getters
    currentSession,
    hasMessages,
    historyForApi,
    // actions
    init,
    createSession,
    switchSession,
    deleteSession,
    addMessage,
    appendToLastAssistant,
    clearMessages,
    setError,
    clearError,
    setAttachment,
    toggleSidebar,
    closeSidebar,
    showToast,
    setPendingHumanAction,
    clearPendingHumanAction,
  }
})