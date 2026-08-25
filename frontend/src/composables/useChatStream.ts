/**
 * SSE 流式聊天 — fetch + ReadableStream 逐行解析。
 *
 * 保留原实现模式（EventSource 不能 POST），封装为可组合 composable。
 * 新增 resume() 方法用于人工中断后恢复工作流。
 */

import { ref } from 'vue'
import type { SSEEvent } from '@/types'

const BASE = import.meta.env.VITE_API_BASE ?? ''

export function useChatStream() {
  const isStreaming = ref(false)
  let abortController: AbortController | null = null

  /**
   * 发送消息并流式接收。
   * @param payload 请求体
   * @param onEvent 事件回调 (chunk / human_choice / human_review / title / done / error)
   */
  async function send(
    payload: Record<string, unknown>,
    onEvent: (evt: SSEEvent) => void,
  ) {
    if (isStreaming.value) return
    isStreaming.value = true
    abortController = new AbortController()

    try {
      const response = await fetch(`${BASE}/api/chat/stream`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
        signal: abortController.signal,
      })

      if (!response.ok) throw new Error(`HTTP ${response.status}`)

      const reader = response.body!.getReader()
      const decoder = new TextDecoder()
      let buffer = ''

      while (true) {
        const { done, value } = await reader.read()
        if (done) break

        buffer += decoder.decode(value, { stream: true })
        const lines = buffer.split('\n')
        buffer = lines.pop() || ''

        for (const line of lines) {
          if (line.startsWith('data: ')) {
            try {
              const data = JSON.parse(line.slice(6)) as SSEEvent
              onEvent(data)
            } catch {
              // skip malformed JSON lines
            }
          }
        }
      }
    } catch (e: any) {
      if (e.name === 'AbortError') return
      onEvent({ type: 'error', message: e.message })
    } finally {
      isStreaming.value = false
      abortController = null
    }
  }

  /**
   * 恢复被中断的工作流（人工选择后调用）。
   * @param sessionId 会话 ID
   * @param actionId 动作 ID
   * @param choice 用户选择
   * @param inputText 可选输入文本（仅 review yes 时需要）
   * @param onEvent 事件回调
   */
  async function resume(
    sessionId: string,
    actionId: string,
    choice: string,
    inputText: string,
    onEvent: (evt: SSEEvent) => void,
  ) {
    if (isStreaming.value) return
    isStreaming.value = true
    abortController = new AbortController()

    try {
      const response = await fetch(`${BASE}/api/chat/resume`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          session_id: sessionId,
          action_id: actionId,
          choice,
          input_text: inputText,
        }),
        signal: abortController.signal,
      })

      if (!response.ok) throw new Error(`HTTP ${response.status}`)

      const reader = response.body!.getReader()
      const decoder = new TextDecoder()
      let buffer = ''

      while (true) {
        const { done, value } = await reader.read()
        if (done) break

        buffer += decoder.decode(value, { stream: true })
        const lines = buffer.split('\n')
        buffer = lines.pop() || ''

        for (const line of lines) {
          if (line.startsWith('data: ')) {
            try {
              const data = JSON.parse(line.slice(6)) as SSEEvent
              onEvent(data)
            } catch {
              // skip malformed JSON lines
            }
          }
        }
      }
    } catch (e: any) {
      if (e.name === 'AbortError') return
      onEvent({ type: 'error', message: e.message })
    } finally {
      isStreaming.value = false
      abortController = null
    }
  }

  function abort() {
    if (abortController) {
      abortController.abort()
      abortController = null
    }
    isStreaming.value = false
  }

  return { isStreaming, send, resume, abort }
}