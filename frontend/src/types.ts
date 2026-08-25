/* ── Session ──────────────────────────────── */
export interface Session {
  id: string
  name: string
  message_count: number
  created_at?: string
  updated_at?: string
}

/* ── Message ──────────────────────────────── */
export interface Message {
  role: 'user' | 'assistant'
  content: string
}

/* ── Attachment (前端侧文件读取) ──────────── */
export interface Attachment {
  name: string
  size: number
  type: string
  content?: string // 文本文件读取后的内容
}

/* ── SSE 事件 ─────────────────────────────── */
export interface SSEChunk {
  type: 'chunk'
  content: string
}

export interface SSETitle {
  type: 'title'
  sessions: Session[]
}

export interface SSEDone {
  type: 'done'
}

export interface SSEError {
  type: 'error'
  message: string
}

export interface SSEHumanChoice {
  type: 'human_choice'
  action_id: string
  options: string[]
}

export interface SSEHumanReview {
  type: 'human_review'
  action_id: string
  options: string[]
  prompt: string
}

export type SSEEvent = SSEChunk | SSETitle | SSEDone | SSEError | SSEHumanChoice | SSEHumanReview

/* ── Chat request payload ─────────────────── */
export interface ChatRequest {
  message: string
  session_id: string
  user_id: number
  history: { role: string; content: string }[]
  attachments?: Pick<Attachment, 'name' | 'size' | 'type'>[]
}

/* ── API responses ────────────────────────── */
export interface InitResponse {
  sessions: Session[]
  current_session_id: string
  history: Message[]
}

export interface SessionResponse {
  session_id: string
  sessions: Session[]
}

export interface DeleteResponse {
  session_id: string
  sessions: Session[]
  history: Message[]
}

export interface HistoryResponse {
  history: Message[]
}

/* ── Toast ────────────────────────────────── */
export interface ToastMessage {
  id: number
  text: string
}