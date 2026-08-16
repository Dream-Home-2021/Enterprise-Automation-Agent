/**
 * 类型化 fetch 封装 — 4 个 REST 接口。
 *
 * API_BASE 取自 VITE_API_BASE env（开发代理或同源）。
 */

import type {
  InitResponse,
  SessionResponse,
  HistoryResponse,
  DeleteResponse,
} from '@/types'

const BASE = import.meta.env.VITE_API_BASE ?? ''

async function get<T>(url: string): Promise<T> {
  const res = await fetch(`${BASE}${url}`)
  if (!res.ok) throw new Error(`HTTP ${res.status}`)
  return res.json()
}

async function post<T>(url: string, body: unknown): Promise<T> {
  const res = await fetch(`${BASE}${url}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  if (!res.ok) throw new Error(`HTTP ${res.status}`)
  return res.json()
}

async function del<T>(url: string): Promise<T> {
  const res = await fetch(`${BASE}${url}`, { method: 'DELETE' })
  if (!res.ok) throw new Error(`HTTP ${res.status}`)
  return res.json()
}

export const api = {
  init: () => get<InitResponse>('/api/init'),
  createSession: () => post<SessionResponse>('/api/sessions', {}),
  getHistory: (sessionId: string) =>
    get<HistoryResponse>(`/api/sessions/${sessionId}/history`),
  deleteSession: (sessionId: string) =>
    del<DeleteResponse>(`/api/sessions/${sessionId}`),
}