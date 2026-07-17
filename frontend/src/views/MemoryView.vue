<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { Check, Download, LoaderCircle, Pencil, Plus, Search, Trash2, Upload, X } from '@lucide/vue'
import {
  createMemory,
  deleteMemory,
  exportMemories,
  importMemories,
  listMemories,
  updateMemory,
  type MemoryItem,
} from '../api/client'

const memories = ref<MemoryItem[]>([])
const loading = ref(true)
const saving = ref(false)
const query = ref('')
const category = ref('')
const editingId = ref<number | null>(null)
const notice = ref<{ kind: 'ok' | 'error'; text: string } | null>(null)
const fileInput = ref<HTMLInputElement | null>(null)
const draft = ref({ content: '', category: 'general', importance: 0.5 })

const filteredCategories = computed(() => [...new Set(memories.value.map(item => item.category))].sort())
const isEditing = computed(() => editingId.value !== null)

function errorMessage(error: any) {
  return error?.response?.data?.detail || error?.message || '操作失败'
}

async function refresh() {
  loading.value = true
  try {
    memories.value = await listMemories({ q: query.value || undefined, category: category.value || undefined })
  } catch (error) {
    notice.value = { kind: 'error', text: errorMessage(error) }
  } finally {
    loading.value = false
  }
}

async function saveDraft() {
  if (!draft.value.content.trim()) {
    notice.value = { kind: 'error', text: '请输入记忆内容' }
    return
  }
  saving.value = true
  notice.value = null
  try {
    if (editingId.value === null) {
      await createMemory({ ...draft.value, content: draft.value.content.trim(), category: draft.value.category.trim() || 'general' })
      notice.value = { kind: 'ok', text: '记忆已添加' }
    } else {
      await updateMemory(editingId.value, { ...draft.value, content: draft.value.content.trim(), category: draft.value.category.trim() || 'general' })
      notice.value = { kind: 'ok', text: '记忆已更新，并已适配当前向量服务' }
    }
    cancelEdit()
    await refresh()
  } catch (error) {
    notice.value = { kind: 'error', text: errorMessage(error) }
  } finally {
    saving.value = false
  }
}

function startEdit(memory: MemoryItem) {
  editingId.value = memory.id
  draft.value = { content: memory.content, category: memory.category, importance: memory.importance }
  notice.value = null
}

function cancelEdit() {
  editingId.value = null
  draft.value = { content: '', category: 'general', importance: 0.5 }
}

async function remove(memory: MemoryItem) {
  if (!window.confirm(`删除这条记忆？\n\n${memory.content.slice(0, 80)}`)) return
  try {
    await deleteMemory(memory.id)
    memories.value = memories.value.filter(item => item.id !== memory.id)
    if (editingId.value === memory.id) cancelEdit()
    notice.value = { kind: 'ok', text: '记忆已删除' }
  } catch (error) {
    notice.value = { kind: 'error', text: errorMessage(error) }
  }
}

async function downloadBackup() {
  try {
    const backup = await exportMemories()
    const blob = new Blob([JSON.stringify(backup, null, 2)], { type: 'application/json' })
    const url = URL.createObjectURL(blob)
    const anchor = document.createElement('a')
    anchor.href = url
    anchor.download = `hyperagent-memories-${new Date().toISOString().slice(0, 10)}.json`
    anchor.click()
    URL.revokeObjectURL(url)
    notice.value = { kind: 'ok', text: `已导出 ${backup.memories.length} 条记忆` }
  } catch (error) {
    notice.value = { kind: 'error', text: errorMessage(error) }
  }
}

function chooseImport() {
  fileInput.value?.click()
}

async function handleImport(event: Event) {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  input.value = ''
  if (!file) return
  try {
    const parsed = JSON.parse(await file.text())
    const imported = Array.isArray(parsed) ? parsed : parsed?.memories
    if (!Array.isArray(imported)) throw new Error('文件中未找到 memories 数组')
    const safeMemories = imported.map((item: any) => ({
      content: String(item?.content || '').trim(),
      category: String(item?.category || 'general').trim() || 'general',
      importance: Math.min(1, Math.max(0, Number(item?.importance ?? 0.5))),
      source: String(item?.source || 'import').slice(0, 50),
    })).filter((item: any) => item.content)
    if (!safeMemories.length) throw new Error('文件中没有有效记忆')
    if (safeMemories.length > 200) throw new Error('一次最多导入 200 条记忆')
    const result = await importMemories(safeMemories)
    notice.value = { kind: 'ok', text: `已导入 ${result.imported} 条，跳过 ${result.skipped} 条重复记忆` }
    await refresh()
  } catch (error: any) {
    notice.value = { kind: 'error', text: error?.message || '导入失败，请使用 HyperAgent 导出的 JSON 文件' }
  }
}

onMounted(refresh)
</script>

<template>
  <div class="memory-page">
    <header class="memory-header">
      <div><h1>记忆</h1><p>管理助手可在对话中使用的长期信息</p></div>
      <div class="header-actions">
        <button class="secondary-button" @click="chooseImport"><Upload :size="16" />导入</button>
        <button class="secondary-button" @click="downloadBackup"><Download :size="16" />导出</button>
        <button class="primary-button" @click="cancelEdit"><Plus :size="16" />添加记忆</button>
        <input ref="fileInput" class="file-input" type="file" accept="application/json,.json" @change="handleImport" />
      </div>
    </header>

    <div v-if="notice" class="notice" :class="notice.kind">
      <Check v-if="notice.kind === 'ok'" :size="16" /><X v-else :size="16" />{{ notice.text }}
    </div>

    <main class="memory-content">
      <section class="editor-section" :class="{ editing: isEditing }">
        <div class="section-heading"><h2>{{ isEditing ? '编辑记忆' : '添加记忆' }}</h2><button v-if="isEditing" class="text-button" @click="cancelEdit">取消编辑</button></div>
        <textarea v-model="draft.content" rows="3" placeholder="例如：我喜欢简洁直接的回答；工作日早上九点开会" />
        <div class="editor-controls">
          <label><span>分类</span><input v-model.trim="draft.category" maxlength="50" /></label>
          <label class="importance"><span>重要性 {{ Math.round(draft.importance * 100) }}%</span><input v-model.number="draft.importance" type="range" min="0" max="1" step="0.1" /></label>
          <button class="primary-button" :disabled="saving" @click="saveDraft"><LoaderCircle v-if="saving" :size="16" class="spin" /><Check v-else :size="16" />{{ isEditing ? '保存修改' : '添加' }}</button>
        </div>
      </section>

      <section class="list-section">
        <div class="list-toolbar">
          <label class="search-input"><Search :size="16" /><input v-model.trim="query" placeholder="搜索记忆" @keyup.enter="refresh" /></label>
          <select v-model="category" @change="refresh"><option value="">全部分类</option><option v-for="item in filteredCategories" :key="item" :value="item">{{ item }}</option></select>
          <button class="icon-button" title="刷新记忆列表" @click="refresh"><LoaderCircle v-if="loading" :size="16" class="spin" /><Search v-else :size="16" /></button>
        </div>
        <div v-if="loading" class="empty-state"><LoaderCircle :size="22" class="spin" /></div>
        <div v-else-if="memories.length" class="memory-list">
          <article v-for="memory in memories" :key="memory.id" class="memory-row">
            <div class="memory-main"><p>{{ memory.content }}</p><div class="memory-meta"><span>{{ memory.category }}</span><span>重要性 {{ Math.round(memory.importance * 100) }}%</span><span>{{ memory.source === 'import' ? '导入' : '对话' }}</span><span v-if="memory.recall_count">已回忆 {{ memory.recall_count }} 次</span></div></div>
            <div class="row-actions"><button class="icon-button" title="编辑记忆" @click="startEdit(memory)"><Pencil :size="16" /></button><button class="icon-button danger" title="删除记忆" @click="remove(memory)"><Trash2 :size="16" /></button></div>
          </article>
        </div>
        <div v-else class="empty-state">还没有符合条件的记忆</div>
      </section>
    </main>
  </div>
</template>

<style scoped>
.memory-page { height: 100vh; overflow-y: auto; color: #20242c; background: #fff; }
.memory-header { min-height: 72px; padding: 14px 32px; border-bottom: 1px solid #e7e9ee; display: flex; align-items: center; justify-content: space-between; gap: 16px; position: sticky; top: 0; z-index: 2; background: rgba(255,255,255,.96); }
h1, h2, p { margin: 0; letter-spacing: 0; } .memory-header h1 { font-size: 20px; font-weight: 650; } .memory-header p { margin-top: 4px; color: #6d7480; font-size: 13px; }
.header-actions, .editor-controls, .list-toolbar, .row-actions { display: flex; align-items: center; gap: 8px; }
.memory-content { max-width: 900px; margin: 0 auto; padding: 28px 32px 48px; }
.editor-section { border-bottom: 1px solid #e7e9ee; padding-bottom: 26px; } .editor-section.editing { border-color: #adc8ff; }
.section-heading { display: flex; align-items: center; justify-content: space-between; margin-bottom: 12px; } .section-heading h2 { font-size: 15px; }
textarea, input, select { border: 1px solid #ccd1da; border-radius: 6px; background: #fff; color: #20242c; font: inherit; font-size: 13px; outline: none; } textarea, .search-input input { width: 100%; padding: 10px 11px; resize: vertical; } input:focus, textarea:focus, select:focus { border-color: #2f6fed; box-shadow: 0 0 0 3px rgba(47,111,237,.1); }
.editor-controls { margin-top: 12px; justify-content: flex-end; } .editor-controls label { display: flex; align-items: center; gap: 8px; color: #59616d; font-size: 12px; } .editor-controls label > input:not([type='range']) { width: 120px; height: 34px; padding: 0 9px; } .importance input { width: 104px; accent-color: #2f6fed; }
.list-section { padding-top: 24px; } .list-toolbar { margin-bottom: 12px; } .search-input { flex: 1; display: flex; align-items: center; gap: 8px; border: 1px solid #ccd1da; border-radius: 6px; padding-left: 10px; color: #6d7480; } .search-input:focus-within { border-color: #2f6fed; box-shadow: 0 0 0 3px rgba(47,111,237,.1); } .search-input input { border: 0; box-shadow: none; } .list-toolbar select { height: 38px; padding: 0 9px; }
.memory-list { border-top: 1px solid #e7e9ee; } .memory-row { display: flex; gap: 16px; align-items: flex-start; padding: 15px 4px; border-bottom: 1px solid #e7e9ee; } .memory-main { min-width: 0; flex: 1; } .memory-main p { font-size: 14px; line-height: 1.55; overflow-wrap: anywhere; } .memory-meta { display: flex; flex-wrap: wrap; gap: 7px; margin-top: 8px; color: #737b87; font-size: 11px; } .memory-meta span { border: 1px solid #e1e4e9; border-radius: 4px; padding: 2px 5px; }
.primary-button, .secondary-button, .icon-button, .text-button { border-radius: 6px; font: inherit; font-size: 13px; cursor: pointer; } .primary-button, .secondary-button { height: 36px; padding: 0 12px; display: inline-flex; align-items: center; gap: 6px; white-space: nowrap; } .primary-button { background: #2f6fed; border: 1px solid #2f6fed; color: #fff; } .secondary-button { background: #fff; border: 1px solid #ccd1da; color: #343a44; } .icon-button { width: 36px; height: 36px; background: #fff; border: 1px solid #ccd1da; color: #59616d; display: grid; place-items: center; } .icon-button.danger:hover { color: #bd3945; border-color: #d99ba1; } .text-button { border: 0; background: transparent; color: #2f6fed; } button:disabled { opacity: .55; cursor: not-allowed; }
.notice { max-width: 900px; margin: 16px auto 0; padding: 10px 13px; border: 1px solid; border-radius: 6px; display: flex; align-items: center; gap: 7px; font-size: 13px; } .notice.ok { color: #286842; background: #edf8f1; border-color: #cce9d6; } .notice.error { color: #a9323c; background: #fff1f2; border-color: #f1cbd0; } .empty-state { min-height: 120px; display: grid; place-items: center; color: #858c97; font-size: 13px; } .file-input { display: none; } .spin { animation: spin .8s linear infinite; } @keyframes spin { to { transform: rotate(360deg); } }
@media (max-width: 760px) { .memory-header { padding: 12px 18px; align-items: flex-start; } .header-actions { flex-wrap: wrap; justify-content: flex-end; } .memory-content { padding: 22px 18px 36px; } .editor-controls { flex-wrap: wrap; justify-content: flex-start; } .list-toolbar { flex-wrap: wrap; } .search-input { min-width: 100%; } .memory-row { padding: 14px 0; } }
</style>
