<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import {
  CheckCircle2,
  Database,
  Eye,
  Globe2,
  History,
  KeyRound,
  LoaderCircle,
  RefreshCw,
  Save,
  Server,
  ShieldCheck,
  Trash2,
  XCircle,
} from '@lucide/vue'
import {
  discoverProviderModels,
  fetchEmbeddingReindex,
  fetchSettings,
  saveSettings,
  startEmbeddingReindex,
  testProviderCapability,
  type ReindexStatus,
  type RuntimeSettings,
} from '../api/client'

const route = useRoute()
const router = useRouter()
const loading = ref(true)
const saving = ref(false)
const discovering = ref(false)
const models = ref<string[]>([])
const llmKey = ref('')
const embeddingKey = ref('')
const githubToken = ref('')
const notionToken = ref('')
const qqEmailAuthCode = ref('')
const weatherApiKey = ref('')
const clearLlmKey = ref(false)
const clearEmbeddingKey = ref(false)
const clearGithubToken = ref(false)
const clearNotionToken = ref(false)
const clearQqEmailAuthCode = ref(false)
const clearWeatherApiKey = ref(false)
const llmKeyConfigured = ref(false)
const embeddingKeyConfigured = ref(false)
const githubTokenConfigured = ref(false)
const notionTokenConfigured = ref(false)
const qqEmailAuthCodeConfigured = ref(false)
const weatherApiKeyConfigured = ref(false)
const notice = ref<{ kind: 'ok' | 'error'; text: string } | null>(null)
const testing = reactive({ chat: false, vision: false, embedding: false })
const testState = reactive<Record<'chat' | 'vision' | 'embedding', string>>({
  chat: '',
  vision: '',
  embedding: '',
})
const reindex = ref<ReindexStatus>({
  state: 'idle', total: 0, indexed: 0, failed: 0, fingerprint: null,
})
let reindexTimer: ReturnType<typeof setInterval> | null = null

const form = reactive({
  provider: 'my_jarvis' as RuntimeSettings['provider'],
  llm_base_url: 'https://api.aijws.com/v1',
  llm_model: 'gpt-5.6-terra',
  vision_use_same_model: true,
  vision_model: '',
  embedding_mode: 'auto' as RuntimeSettings['embedding_mode'],
  embedding_base_url: 'https://openrouter.ai/api/v1',
  embedding_model: 'qwen/qwen3-embedding-8b',
  embedding_auto_model: 'text-embedding-3-small',
  search_engine_url: '',
  timezone: 'Asia/Shanghai',
  max_history_messages: 40,
  assistant_style: 'balanced' as RuntimeSettings['assistant_style'],
  weather_base_url: 'https://api.openweathermap.org/data/2.5',
  github_username: '',
  qq_email_address: '',
})

const providerOptions = [
  {
    value: 'my_jarvis',
    label: '我的贾维斯',
    url: 'https://api.aijws.com/v1',
    model: 'gpt-5.6-terra',
  },
  {
    value: 'openai',
    label: 'OpenAI 官方',
    url: 'https://api.openai.com/v1',
    model: 'gpt-5.6-terra',
  },
  { value: 'custom', label: '自定义兼容接口', url: '', model: '' },
] as const

const firstRun = computed(() => route.query.firstRun === '1')
const visionModel = computed(() => form.vision_use_same_model ? form.llm_model : form.vision_model)
const availableModels = computed(() => {
  return [...new Set([
    ...models.value,
    form.llm_model,
    form.vision_model,
  ].filter(Boolean))].sort()
})
const progress = computed(() => reindex.value.total
  ? Math.round((reindex.value.indexed + reindex.value.failed) / reindex.value.total * 100)
  : 0)

function applySettings(data: RuntimeSettings) {
  form.provider = data.provider
  form.llm_base_url = data.llm_base_url
  form.llm_model = data.llm_model
  form.vision_use_same_model = data.vision_use_same_model
  form.vision_model = data.vision_model
  form.embedding_mode = data.embedding_mode
  form.embedding_base_url = data.embedding_base_url
  form.embedding_model = data.embedding_model
  form.embedding_auto_model = data.embedding_auto_model
  form.search_engine_url = data.search_engine_url
  form.timezone = data.timezone
  form.max_history_messages = data.max_history_messages
  form.assistant_style = data.assistant_style
  form.weather_base_url = data.weather_base_url
  form.github_username = data.github_username
  form.qq_email_address = data.qq_email_address
  llmKeyConfigured.value = data.llm_api_key_configured
  embeddingKeyConfigured.value = data.embedding_api_key_configured
  githubTokenConfigured.value = data.github_token_configured
  notionTokenConfigured.value = data.notion_token_configured
  qqEmailAuthCodeConfigured.value = data.qq_email_auth_code_configured
  weatherApiKeyConfigured.value = data.weather_api_key_configured
  reindex.value = data.reindex
}

onMounted(async () => {
  try {
    applySettings(await fetchSettings())
    if (reindex.value.state === 'running') startReindexPolling()
  } catch (error: any) {
    setError(error)
  } finally {
    loading.value = false
  }
})

onBeforeUnmount(() => {
  if (reindexTimer) clearInterval(reindexTimer)
})

function changeProvider() {
  const preset = providerOptions.find(option => option.value === form.provider)
  if (preset) {
    form.llm_base_url = preset.url
    form.llm_model = preset.model
  }
  models.value = []
  testState.chat = testState.vision = ''
}

function errorMessage(error: any): string {
  return error?.response?.data?.detail || error?.message || '请求失败'
}

function setError(error: any) {
  notice.value = { kind: 'error', text: errorMessage(error) }
}

async function refreshModels() {
  discovering.value = true
  notice.value = null
  try {
    models.value = await discoverProviderModels(form.llm_base_url, llmKey.value || undefined)
    if (!models.value.length) {
      notice.value = { kind: 'error', text: '接口未返回可用模型' }
    } else {
      notice.value = { kind: 'ok', text: `已获取 ${models.value.length} 个可用模型` }
    }
  } catch (error) {
    setError(error)
  } finally {
    discovering.value = false
  }
}

async function runTest(kind: 'chat' | 'vision' | 'embedding') {
  testing[kind] = true
  testState[kind] = ''
  try {
    const isEmbedding = kind === 'embedding'
    const result = await testProviderCapability({
      kind,
      base_url: isEmbedding ? form.embedding_base_url : form.llm_base_url,
      model: isEmbedding ? form.embedding_model : (kind === 'vision' ? visionModel.value : form.llm_model),
      api_key: isEmbedding ? (embeddingKey.value || undefined) : (llmKey.value || undefined),
    })
    testState[kind] = isEmbedding
      ? `连接正常，向量维度 ${result.dimensions}`
      : `已通过 ${result.checks.join(' / ')} 测试`
  } catch (error) {
    testState[kind] = errorMessage(error)
  } finally {
    testing[kind] = false
  }
}

async function handleSave() {
  saving.value = true
  notice.value = null
  try {
    const result = await saveSettings({
      ...form,
      llm_reasoning_effort: 'none',
      ...(llmKey.value ? { llm_api_key: llmKey.value } : {}),
      ...(embeddingKey.value ? { embedding_api_key: embeddingKey.value } : {}),
      ...(githubToken.value ? { github_token: githubToken.value } : {}),
      ...(notionToken.value ? { notion_token: notionToken.value } : {}),
      ...(qqEmailAuthCode.value ? { qq_email_auth_code: qqEmailAuthCode.value } : {}),
      ...(weatherApiKey.value ? { weather_api_key: weatherApiKey.value } : {}),
      ...(clearLlmKey.value ? { clear_llm_api_key: true } : {}),
      ...(clearEmbeddingKey.value ? { clear_embedding_api_key: true } : {}),
      ...(clearGithubToken.value ? { clear_github_token: true } : {}),
      ...(clearNotionToken.value ? { clear_notion_token: true } : {}),
      ...(clearQqEmailAuthCode.value ? { clear_qq_email_auth_code: true } : {}),
      ...(clearWeatherApiKey.value ? { clear_weather_api_key: true } : {}),
    })
    applySettings(result)
    llmKey.value = ''
    embeddingKey.value = ''
    githubToken.value = notionToken.value = qqEmailAuthCode.value = weatherApiKey.value = ''
    clearLlmKey.value = clearEmbeddingKey.value = false
    clearGithubToken.value = clearNotionToken.value = false
    clearQqEmailAuthCode.value = clearWeatherApiKey.value = false
    notice.value = { kind: 'ok', text: '设置已保存并生效' }
    if (firstRun.value && !result.needs_setup) {
      await router.replace('/')
    }
  } catch (error) {
    setError(error)
  } finally {
    saving.value = false
  }
}

function requestClear(kind: 'llm' | 'embedding' | 'github' | 'notion' | 'qq' | 'weather') {
  const label = {
    llm: '聊天 API Key', embedding: 'Embedding API Key', github: 'GitHub Token',
    notion: 'Notion Token', qq: 'QQ 邮箱授权码', weather: 'OpenWeatherMap API Key',
  }[kind]
  if (!window.confirm(`确定清除${label}？`)) return
  if (kind === 'llm') {
    clearLlmKey.value = true
    llmKey.value = ''
  } else if (kind === 'embedding') {
    clearEmbeddingKey.value = true
    embeddingKey.value = ''
  } else if (kind === 'github') {
    clearGithubToken.value = true
    githubToken.value = ''
  } else if (kind === 'notion') {
    clearNotionToken.value = true
    notionToken.value = ''
  } else if (kind === 'qq') {
    clearQqEmailAuthCode.value = true
    qqEmailAuthCode.value = ''
  } else {
    clearWeatherApiKey.value = true
    weatherApiKey.value = ''
  }
}

async function rebuildEmbeddings() {
  try {
    reindex.value = await startEmbeddingReindex()
    startReindexPolling()
  } catch (error) {
    setError(error)
  }
}

function startReindexPolling() {
  if (reindexTimer) clearInterval(reindexTimer)
  reindexTimer = setInterval(async () => {
    try {
      reindex.value = await fetchEmbeddingReindex()
      if (reindex.value.state !== 'running' && reindexTimer) {
        clearInterval(reindexTimer)
        reindexTimer = null
      }
    } catch { /* retain the last known progress */ }
  }, 1000)
}
</script>

<template>
  <div class="settings-page">
    <header class="settings-header">
      <div>
        <h1>设置</h1>
        <p v-if="firstRun">配置模型服务后即可开始对话</p>
      </div>
      <button class="primary-button" :disabled="loading || saving" @click="handleSave">
        <LoaderCircle v-if="saving" :size="17" class="spin" />
        <Save v-else :size="17" />
        保存
      </button>
    </header>

    <div v-if="notice" class="notice" :class="notice.kind">
      <CheckCircle2 v-if="notice.kind === 'ok'" :size="17" />
      <XCircle v-else :size="17" />
      {{ notice.text }}
    </div>

    <main v-if="!loading" class="settings-content">
      <section class="settings-section">
        <div class="section-title">
          <Server :size="20" />
          <div><h2>模型服务</h2><p>聊天与工具调用</p></div>
        </div>
        <div class="form-grid">
          <label class="field">
            <span>供应商</span>
            <select v-model="form.provider" @change="changeProvider">
              <option v-for="option in providerOptions" :key="option.value" :value="option.value">{{ option.label }}</option>
            </select>
          </label>
          <label class="field span-2">
            <span>Base URL</span>
            <input v-model.trim="form.llm_base_url" type="url" autocomplete="off" />
          </label>
          <label class="field span-2">
            <span>API Key</span>
            <div class="input-row">
              <input v-model="llmKey" type="password" autocomplete="new-password" :placeholder="llmKeyConfigured ? '已配置，留空保持不变' : '输入 API Key'" />
              <button v-if="llmKeyConfigured" class="icon-button danger" title="清除聊天 API Key" @click="requestClear('llm')"><Trash2 :size="17" /></button>
            </div>
          </label>
          <label class="field span-2">
            <span>聊天模型</span>
            <div class="input-row model-picker">
              <input
                v-model.trim="form.llm_model"
                list="provider-model-options"
                autocomplete="off"
                placeholder="输入模型 ID，或点击右侧刷新"
                :disabled="discovering"
              />
              <button
                class="icon-button"
                :disabled="discovering"
                title="根据当前 Base URL 和 API Key 刷新可用模型"
                aria-label="刷新可用模型"
                @click="refreshModels"
              >
                <RefreshCw :size="16" :class="{ spin: discovering }" />
              </button>
            </div>
            <datalist id="provider-model-options">
              <option v-for="model in availableModels" :key="model" :value="model" />
            </datalist>
          </label>
        </div>
        <div class="action-line">
          <button class="secondary-button" :disabled="testing.chat" @click="runTest('chat')">
            <LoaderCircle v-if="testing.chat" :size="16" class="spin" /><ShieldCheck v-else :size="16" />
            测试聊天与工具
          </button>
          <span class="test-result" :class="{ error: testState.chat && !testState.chat.startsWith('已通过') }">{{ testState.chat }}</span>
        </div>
      </section>

      <section class="settings-section">
        <div class="section-title">
          <Eye :size="20" />
          <div><h2>视觉模型</h2><p>图片理解</p></div>
        </div>
        <label class="toggle-row">
          <input v-model="form.vision_use_same_model" type="checkbox" />
          <span>与聊天模型相同</span>
        </label>
        <label v-if="!form.vision_use_same_model" class="field compact-field">
          <span>视觉模型</span>
          <input
            v-model.trim="form.vision_model"
            list="provider-model-options"
            autocomplete="off"
            placeholder="输入视觉模型 ID"
          />
        </label>
        <div class="action-line">
          <button class="secondary-button" :disabled="testing.vision" @click="runTest('vision')">
            <LoaderCircle v-if="testing.vision" :size="16" class="spin" /><Eye v-else :size="16" />
            测试图片输入
          </button>
          <span class="test-result" :class="{ error: testState.vision && !testState.vision.startsWith('已通过') }">{{ testState.vision }}</span>
        </div>
      </section>

      <section class="settings-section">
        <div class="section-title">
          <Database :size="20" />
          <div><h2>Embedding</h2><p>记忆语义检索</p></div>
        </div>
        <div class="form-grid">
          <label class="field">
            <span>模式</span>
            <select v-model="form.embedding_mode">
              <option value="auto">自动检测并回退</option>
              <option value="separate">仅使用独立服务</option>
              <option value="disabled">关闭向量检索</option>
            </select>
          </label>
          <label v-if="form.embedding_mode === 'auto'" class="field">
            <span>自动检测模型</span>
            <input v-model.trim="form.embedding_auto_model" autocomplete="off" />
          </label>
          <template v-if="form.embedding_mode !== 'disabled'">
            <label class="field span-2"><span>回退 Base URL</span><input v-model.trim="form.embedding_base_url" type="url" autocomplete="off" /></label>
            <label class="field"><span>回退模型</span><input v-model.trim="form.embedding_model" autocomplete="off" /></label>
            <label class="field">
              <span>Embedding API Key</span>
              <div class="input-row">
                <input v-model="embeddingKey" type="password" autocomplete="new-password" :placeholder="embeddingKeyConfigured ? '已配置，留空保持不变' : '输入 API Key'" />
                <button v-if="embeddingKeyConfigured" class="icon-button danger" title="清除 Embedding API Key" @click="requestClear('embedding')"><Trash2 :size="17" /></button>
              </div>
            </label>
          </template>
        </div>
        <div v-if="form.embedding_mode !== 'disabled'" class="action-line">
          <button class="secondary-button" :disabled="testing.embedding" @click="runTest('embedding')">
            <LoaderCircle v-if="testing.embedding" :size="16" class="spin" /><KeyRound v-else :size="16" />
            测试回退服务
          </button>
          <span class="test-result" :class="{ error: testState.embedding && !testState.embedding.startsWith('连接正常') }">{{ testState.embedding }}</span>
        </div>
        <div class="reindex-row">
          <div>
            <span>记忆索引</span>
            <small>{{ reindex.indexed }}/{{ reindex.total }} 已完成<span v-if="reindex.failed">，{{ reindex.failed }} 失败</span></small>
          </div>
          <div v-if="reindex.state === 'running'" class="progress"><span :style="{ width: `${progress}%` }"></span></div>
          <button class="secondary-button" :disabled="reindex.state === 'running' || form.embedding_mode === 'disabled'" @click="rebuildEmbeddings">
            <RefreshCw :size="16" :class="{ spin: reindex.state === 'running' }" />
            重建索引
          </button>
        </div>
      </section>

      <section class="settings-section">
        <div class="section-title">
          <KeyRound :size="20" />
          <div><h2>第三方集成</h2><p>GitHub、Notion 与 QQ 邮箱</p></div>
        </div>
        <div class="form-grid">
          <label class="field">
            <span>GitHub 用户名</span>
            <input v-model.trim="form.github_username" autocomplete="username" placeholder="可选，用于个人标识" />
          </label>
          <label class="field">
            <span>GitHub Token</span>
            <div class="input-row">
              <input v-model="githubToken" type="password" autocomplete="new-password" :placeholder="githubTokenConfigured ? '已配置，留空保持不变' : '输入 Personal Access Token'" />
              <button v-if="githubTokenConfigured" class="icon-button danger" title="清除 GitHub Token" @click="requestClear('github')"><Trash2 :size="17" /></button>
            </div>
          </label>
          <label class="field span-2">
            <span>Notion Token</span>
            <div class="input-row">
              <input v-model="notionToken" type="password" autocomplete="new-password" :placeholder="notionTokenConfigured ? '已配置，留空保持不变' : '输入 Notion Integration Token'" />
              <button v-if="notionTokenConfigured" class="icon-button danger" title="清除 Notion Token" @click="requestClear('notion')"><Trash2 :size="17" /></button>
            </div>
          </label>
          <label class="field">
            <span>QQ 邮箱地址</span>
            <input v-model.trim="form.qq_email_address" type="email" autocomplete="email" placeholder="name@qq.com" />
          </label>
          <label class="field">
            <span>QQ 邮箱授权码</span>
            <div class="input-row">
              <input v-model="qqEmailAuthCode" type="password" autocomplete="new-password" :placeholder="qqEmailAuthCodeConfigured ? '已配置，留空保持不变' : '输入 QQ 邮箱授权码'" />
              <button v-if="qqEmailAuthCodeConfigured" class="icon-button danger" title="清除 QQ 邮箱授权码" @click="requestClear('qq')"><Trash2 :size="17" /></button>
            </div>
          </label>
        </div>
      </section>

      <section class="settings-section">
        <div class="section-title">
          <Globe2 :size="20" />
          <div><h2>网络与地区</h2><p>搜索、天气和时间解析</p></div>
        </div>
        <div class="form-grid">
          <label class="field span-2">
            <span>自定义搜索服务 URL</span>
            <input v-model.trim="form.search_engine_url" type="url" autocomplete="off" placeholder="可选，例如 SearXNG 地址；留空使用内置搜索" />
          </label>
          <label class="field">
            <span>时区</span>
            <input v-model.trim="form.timezone" autocomplete="off" placeholder="Asia/Shanghai" />
          </label>
          <label class="field">
            <span>天气服务地址</span>
            <input v-model.trim="form.weather_base_url" type="url" autocomplete="off" />
          </label>
          <label class="field span-2">
            <span>OpenWeatherMap API Key</span>
            <div class="input-row">
              <input v-model="weatherApiKey" type="password" autocomplete="new-password" :placeholder="weatherApiKeyConfigured ? '已配置，留空保持不变' : '可选，输入后使用 OpenWeatherMap'" />
              <button v-if="weatherApiKeyConfigured" class="icon-button danger" title="清除天气 API Key" @click="requestClear('weather')"><Trash2 :size="17" /></button>
            </div>
          </label>
        </div>
      </section>

      <section class="settings-section">
        <div class="section-title">
          <History :size="20" />
          <div><h2>对话偏好</h2><p>回复风格与每轮历史消息数量</p></div>
        </div>
        <div class="form-grid">
          <label class="field">
            <span>助手回复风格</span>
            <select v-model="form.assistant_style">
              <option value="concise">简洁</option>
              <option value="balanced">均衡</option>
              <option value="detailed">详细</option>
            </select>
          </label>
          <label class="field">
            <span>历史消息上限</span>
            <input v-model.number="form.max_history_messages" type="number" min="0" max="500" step="1" />
            <small>设为 0 时不裁剪历史；较小的值可减少模型调用成本。</small>
          </label>
        </div>
      </section>
    </main>

    <div v-else class="page-loading"><LoaderCircle :size="24" class="spin" /></div>
  </div>
</template>

<style scoped>
.settings-page { height: 100vh; overflow-y: auto; background: #fff; color: #20242c; }
.settings-header { min-height: 72px; padding: 14px 32px; border-bottom: 1px solid #e7e9ee; display: flex; align-items: center; justify-content: space-between; gap: 16px; position: sticky; top: 0; background: rgba(255,255,255,.96); z-index: 2; }
.settings-header h1 { margin: 0; font-size: 20px; font-weight: 650; letter-spacing: 0; }
.settings-header p { margin: 4px 0 0; color: #6d7480; font-size: 13px; }
.settings-content { max-width: 900px; margin: 0 auto; padding: 8px 32px 44px; }
.settings-section { display: grid; grid-template-columns: 210px minmax(0, 1fr); gap: 24px; padding: 30px 0; border-bottom: 1px solid #eceef2; }
.section-title { display: flex; gap: 11px; align-items: flex-start; color: #2f6fed; }
.section-title h2 { color: #252a33; font-size: 15px; margin: 0; letter-spacing: 0; }
.section-title p { color: #818894; font-size: 12px; margin: 5px 0 0; }
.form-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 18px; }
.field { min-width: 0; display: flex; flex-direction: column; gap: 7px; font-size: 13px; color: #4f5662; }
.field.span-2 { grid-column: span 2; }
.compact-field { max-width: 480px; }
input, select { width: 100%; min-width: 0; height: 38px; border: 1px solid #ccd1da; border-radius: 6px; background: #fff; color: #20242c; font: inherit; padding: 0 11px; outline: none; letter-spacing: 0; }
input:focus, select:focus { border-color: #2f6fed; box-shadow: 0 0 0 3px rgba(47,111,237,.1); }
.input-row { display: flex; gap: 8px; min-width: 0; }
.model-picker select, .model-picker input { flex: 1; }
.icon-button { width: 38px; height: 38px; flex: 0 0 38px; border: 1px solid #ccd1da; border-radius: 6px; background: #fff; color: #5e6672; display: grid; place-items: center; cursor: pointer; }
.icon-button:hover { border-color: #2f6fed; color: #2f6fed; }
.icon-button.danger:hover { color: #c53d48; border-color: #d99ba1; }
.primary-button, .secondary-button { height: 36px; border-radius: 6px; display: inline-flex; align-items: center; justify-content: center; gap: 7px; padding: 0 14px; font: inherit; font-size: 13px; cursor: pointer; white-space: nowrap; }
.primary-button { border: 1px solid #2f6fed; background: #2f6fed; color: #fff; }
.secondary-button { border: 1px solid #ccd1da; background: #fff; color: #343a44; }
.primary-button:hover:not(:disabled) { background: #245dcc; }
.secondary-button:hover:not(:disabled) { border-color: #8d96a5; background: #f7f8fa; }
button:disabled { opacity: .55; cursor: not-allowed; }
.action-line { grid-column: 2; display: flex; align-items: center; gap: 12px; margin-top: -8px; }
.test-result { color: #2f7b51; font-size: 12px; overflow-wrap: anywhere; }
.test-result.error { color: #bd3945; }
.toggle-row { grid-column: 2; display: flex; align-items: center; gap: 9px; font-size: 13px; color: #3e454f; }
.toggle-row input { width: 16px; height: 16px; accent-color: #2f6fed; }
.settings-section > .compact-field { grid-column: 2; }
.reindex-row { grid-column: 2; border-top: 1px solid #eceef2; padding-top: 18px; display: grid; grid-template-columns: minmax(120px, 1fr) minmax(90px, 180px) auto; align-items: center; gap: 14px; }
.reindex-row > div:first-child { display: flex; flex-direction: column; gap: 4px; font-size: 13px; }
.reindex-row small { color: #858c97; font-size: 11px; }
.progress { height: 5px; background: #e8ebf0; overflow: hidden; border-radius: 3px; }
.progress span { display: block; height: 100%; background: #2f6fed; }
.notice { max-width: 900px; margin: 16px auto 0; padding: 10px 13px; border-radius: 6px; display: flex; align-items: center; gap: 8px; font-size: 13px; }
.notice.ok { background: #edf8f1; color: #286842; border: 1px solid #cce9d6; }
.notice.error { background: #fff1f2; color: #a9323c; border: 1px solid #f1cbd0; }
.page-loading { height: 50vh; display: grid; place-items: center; color: #2f6fed; }
.spin { animation: spin .8s linear infinite; }
@keyframes spin { to { transform: rotate(360deg); } }
@media (max-width: 760px) {
  .settings-header { padding: 12px 18px; }
  .settings-content { padding: 4px 18px 36px; }
  .settings-section { grid-template-columns: 1fr; gap: 18px; }
  .section-title, .action-line, .toggle-row, .settings-section > .compact-field, .reindex-row { grid-column: 1; }
  .form-grid { grid-template-columns: 1fr; }
  .field.span-2 { grid-column: 1; }
  .reindex-row { grid-template-columns: 1fr auto; }
  .progress { grid-column: 1 / -1; grid-row: 2; }
}
</style>
