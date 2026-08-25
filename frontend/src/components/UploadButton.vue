<script setup lang="ts">
/**
 * 隐藏的文件上传按钮 — 回形针图标。
 */
import { ref } from 'vue'
import { useChatStore } from '@/stores/chat'
import type { Attachment } from '@/types'

const store = useChatStore()
const fileInput = ref<HTMLInputElement | null>(null)

/** 文本文件类型白名单（按扩展名校验）。 */
const TEXT_EXTENSIONS = new Set([
  'txt', 'md', 'py', 'js', 'json', 'csv', 'log', 'yml', 'yaml',
  'ts', 'html', 'css', 'xml', 'cfg', 'conf', 'ini', 'env', 'toml',
  'sql', 'sh', 'bat', 'ps1', 'vue', 'svelte', 'jsx', 'tsx',
  'java', 'c', 'cpp', 'h', 'hpp', 'go', 'rs', 'rb', 'php', 'swift',
])

const MAX_BYTES = 5 * 1024 * 1024 // 5MB

function getExtension(name: string): string {
  const i = name.lastIndexOf('.')
  return i > 0 ? name.slice(i + 1).toLowerCase() : ''
}

function isTextFile(file: File): boolean {
  const ext = getExtension(file.name)
  if (!ext) return false
  return TEXT_EXTENSIONS.has(ext)
}

function formatSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}

async function handleFileChange(event: Event) {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  if (!file) return

  const att: Attachment = {
    name: file.name,
    size: file.size,
    type: file.type || getExtension(file.name),
    content: undefined,
  }

  if (file.size > MAX_BYTES) {
    store.showToast('文件过大（超过 5MB），仅附加文件名')
  } else if (isTextFile(file)) {
    try {
      att.content = await file.text()
    } catch {
      store.showToast('文件读取失败')
    }
  }

  store.setAttachment(att)
  // Reset so the same file can be re-selected
  input.value = ''
}

function triggerFilePicker() {
  fileInput.value?.click()
}
</script>

<template>
  <button class="upload-btn" @click="triggerFilePicker" title="上传文件" aria-label="上传文件">
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
      <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/>
      <polyline points="17 8 12 3 7 8"/>
      <line x1="12" y1="3" x2="12" y2="15"/>
    </svg>
  </button>
  <input
    ref="fileInput"
    type="file"
    class="visually-hidden"
    @change="handleFileChange"
    accept="*"
  />
</template>

<style scoped>
.upload-btn {
  width: 36px;
  height: 36px;
  border-radius: 50%;
  border: none;
  background: transparent;
  color: var(--text-dim);
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  transition: background 0.15s, color 0.15s;
}
.upload-btn:hover {
  background: rgba(255,255,255,0.06);
  color: var(--text);
}
.upload-btn svg {
  width: 18px;
  height: 18px;
}
</style>