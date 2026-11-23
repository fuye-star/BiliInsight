<script setup lang="ts">
/**
 * AI 助手页 —— RAG 对话助手 + 批量情感分析。
 *
 * 【页面结构】
 *   左栏：对话区
 *     · 消息列表（用户 / AI，AI 消息下方展示引用来源）
 *     · 流式打字效果
 *     · 示例问题快捷入口
 *     · 输入框（Enter 发送，Shift+Enter 换行）
 *   右栏：链路状态 + 批量情感分析
 *     · 向量索引状态 / 大模型 Provider 状态
 *     · 未就绪时给出明确的操作指引
 *     · 一键重建索引
 *
 * 【流式实现要点】
 * 用 fetch + ReadableStream 而非 EventSource（后者不支持 POST）。
 * 见 api/request.ts 的 postStream()。
 */
import { computed, nextTick, onMounted, ref } from 'vue'

import EChart from '@/components/EChart.vue'
import ModelProviderDialog from '@/components/ModelProviderDialog.vue'
import { aiApi } from '@/api'
import { postStream, withErrorToast } from '@/api/request'
import { buildSentimentPieOption } from '@/utils/chartOptions'
import { formatDate, formatNumber, formatPercent, sentimentColor } from '@/utils/format'

import type {
  ChatStreamEvent,
  RagSource,
  RagStatus,
  SentimentAnalyzeResult,
  SentimentDistributionItem,
} from '@/types'

// ===========================================================================
// 对话状态
// ===========================================================================
/** 本地消息结构（比后端模型多了流式状态） */
interface LocalMessage {
  role: 'user' | 'assistant'
  content: string
  sources: RagSource[]
  /** 是否正在流式生成中 */
  streaming?: boolean
  /** 使用的 Provider */
  provider?: string
  /** 响应耗时（毫秒） */
  latency?: number
  /** 是否走了检索兜底 */
  fallback?: boolean
  /** 错误信息 */
  error?: string
  time: string
}

const messages = ref<LocalMessage[]>([])
const inputText = ref('')
const sending = ref(false)
const sessionId = ref<number | null>(null)
const messageListRef = ref<HTMLElement | null>(null)

/**
 * 模型提供商设置弹窗。
 *
 * 【为什么入口放在 AI 页面】
 *   用户"发现 AI 不够聪明/没接入大模型"的瞬间就在这里。
 *   把设置入口放在同一个页面，不用去翻设置菜单，路径最短。
 *   右侧状态面板里也会提示"还没有配置大模型，点「模型设置」"。
 */
const providerDialogVisible = ref(false)

/** 配置变更后刷新状态面板（模型名、可用性都会变） */
async function onProviderChanged() {
  await loadStatus()
}

/** 中止控制器，用于"停止生成" */
let abortController: AbortController | null = null

/** 示例问题：覆盖排行 / 推荐 / 选题三类意图，便于演示 */
const examples = [
  '科技区有什么值得看的视频',
  '推荐适合下饭的搞笑视频',
  '最近哪些视频播放量最高',
  '给我一些创作者选题建议',
]

const hasMessages = computed(() => messages.value.length > 0)

/** 滚动到底部 */
async function scrollToBottom() {
  await nextTick()
  const el = messageListRef.value
  if (el) {
    el.scrollTop = el.scrollHeight
  }
}

/**
 * 发送消息并接收流式回答。
 */
async function send() {
  const query = inputText.value.trim()
  if (!query || sending.value) return

  // 固定当前时间，避免流式过程中时间戳变动
  const now = new Date().toISOString()

  messages.value.push({
    role: 'user',
    content: query,
    sources: [],
    time: now,
  })

  inputText.value = ''
  sending.value = true
  await scrollToBottom()

  // 先插入一条空的助手消息，随后往里追加流式片段
  const assistantMessage: LocalMessage = {
    role: 'assistant',
    content: '',
    sources: [],
    streaming: true,
    time: new Date().toISOString(),
  }
  messages.value.push(assistantMessage)
  await scrollToBottom()

  abortController = new AbortController()

  try {
    await postStream(
      '/ai/chat/',
      {
        query,
        session_id: sessionId.value,
        top_k: 5,
        stream: true,
        save: true,
      },
      (event) => {
        const evt = event as unknown as ChatStreamEvent

        if (evt.type === 'meta') {
          // 元信息先到：立刻渲染引用来源，用户不必等正文
          assistantMessage.sources = evt.data.sources ?? []
          assistantMessage.provider = evt.data.provider
          assistantMessage.fallback = evt.data.fallback
        } else if (evt.type === 'chunk') {
          assistantMessage.content += evt.data
          scrollToBottom()
        } else if (evt.type === 'done') {
          assistantMessage.streaming = false
          assistantMessage.latency = evt.data.latency_ms
          if (evt.data.provider) assistantMessage.provider = evt.data.provider
          // done 帧可能带上完整 answer，用它兜底防止片段丢字
          if (evt.data.answer && evt.data.answer.length > assistantMessage.content.length) {
            assistantMessage.content = evt.data.answer
          }
        } else if (evt.type === 'error') {
          assistantMessage.streaming = false
          assistantMessage.error = String(evt.data)
        }
      },
      abortController.signal,
    )
  } catch (error) {
    assistantMessage.streaming = false
    // 用户主动中止不算错误
    if ((error as Error)?.name === 'AbortError') {
      assistantMessage.content += '\n\n（已停止生成）'
    } else {
      assistantMessage.error =
        error instanceof Error ? error.message : '请求失败，请检查后端服务'
    }
  } finally {
    sending.value = false
    abortController = null
    await scrollToBottom()
    // 会话建立后刷新状态（会话数变化）
    loadStatus()
  }
}

/** 停止生成 */
function stopGenerating() {
  abortController?.abort()
}

/** 用示例问题填充并发送 */
function useExample(text: string) {
  inputText.value = text
  send()
}

/** 开始新会话 */
function newSession() {
  sessionId.value = null
  messages.value = []
}

/** 在B站打开引用视频 */
function openSource(bvid: string) {
  window.open(`https://www.bilibili.com/video/${bvid}`, '_blank')
}

// ===========================================================================
// RAG 状态
// ===========================================================================
const status = ref<RagStatus | null>(null)
const statusLoading = ref(false)
const building = ref(false)

async function loadStatus() {
  statusLoading.value = true
  status.value = await withErrorToast(() => aiApi.status(), null, { silent: true })
  statusLoading.value = false
}

/** 重建向量索引 */
async function rebuildIndex() {
  building.value = true
  const result = await withErrorToast(() => aiApi.buildIndex(true), null)
  building.value = false

  if (result) {
    await loadStatus()
  }
}

/** 状态标签 */
const statusTag = computed(() => {
  const s = status.value
  if (!s) return { type: 'info' as const, text: '状态未知' }
  if (!s.index.ready) return { type: 'danger' as const, text: '索引未构建' }
  if (s.fallback) return { type: 'warning' as const, text: '未接入大模型' }
  return { type: 'success' as const, text: '已就绪' }
})

// ===========================================================================
// 批量情感分析（阶段三已有功能，保留在右栏）
// ===========================================================================
const sentimentText = ref('')
const sentimentAnalyzing = ref(false)
const sentimentResults = ref<SentimentAnalyzeResult[]>([])

const MAX_BATCH = 200

const sentimentLineCount = computed(
  () => sentimentText.value.split('\n').filter((l) => l.trim()).length,
)

async function analyzeSentiment() {
  const texts = sentimentText.value
    .split('\n')
    .map((l) => l.trim())
    .filter(Boolean)

  if (!texts.length || texts.length > MAX_BATCH) return

  sentimentAnalyzing.value = true
  sentimentResults.value = []

  const data = await withErrorToast(() => aiApi.analyzeSentiment({ texts }), null)
  if (data) {
    sentimentResults.value = (data.results ?? []) as SentimentAnalyzeResult[]
  }
  sentimentAnalyzing.value = false
}

const sentimentDistribution = computed<SentimentDistributionItem[]>(() => {
  const counter: Record<string, number> = { positive: 0, neutral: 0, negative: 0 }
  for (const r of sentimentResults.value) {
    if (r.label in counter) counter[r.label] += 1
  }
  const total = sentimentResults.value.length || 1
  const names: Record<string, string> = { positive: '正向', neutral: '中性', negative: '负向' }
  return (['positive', 'neutral', 'negative'] as const).map((label) => ({
    label,
    name: names[label],
    count: counter[label],
    pct: Number(((counter[label] / total) * 100).toFixed(2)),
  }))
})

const sentimentPieOption = computed(() => buildSentimentPieOption(sentimentDistribution.value))

onMounted(() => {
  loadStatus()
})
</script>

<template>
  <div class="page-container">
    <el-row :gutter="16">
      <!-- ==================== 左栏：对话区 ==================== -->
      <el-col :xs="24" :lg="16" style="margin-bottom: 16px">
        <el-card shadow="never" class="chat-card">
          <template #header>
            <div class="card-header">
              <div style="display: flex; align-items: center; gap: 10px">
                <span>AI 推荐助手</span>
                <el-tag :type="statusTag.type" size="small" effect="light">
                  {{ statusTag.text }}
                </el-tag>
                <el-tag v-if="status?.llm.provider" size="small" effect="plain">
                  {{ status.llm.provider }}
                </el-tag>
              </div>

              <div>
                <el-button
                  v-if="hasMessages"
                  size="small"
                  :icon="'Plus'"
                  @click="newSession"
                >
                  新会话
                </el-button>
                <el-button
                  size="small"
                  :icon="'Refresh'"
                  :loading="statusLoading"
                  @click="loadStatus"
                />
              </div>
            </div>
          </template>

          <!-- ---- 消息列表 ---- -->
          <div ref="messageListRef" class="chat-messages">
            <!-- 空状态：展示能力说明与示例问题 -->
            <div v-if="!hasMessages" class="chat-empty">
              <el-icon :size="42" color="#c0c4cc"><ChatDotRound /></el-icon>
              <h3>问我关于B站视频数据的任何问题</h3>
              <p class="text-muted">
                我会先在你的视频库中检索相关内容，再基于检索结果回答，并标注引用来源。
              </p>

              <div class="example-list">
                <el-tag
                  v-for="ex in examples"
                  :key="ex"
                  class="example-tag"
                  effect="plain"
                  @click="useExample(ex)"
                >
                  {{ ex }}
                </el-tag>
              </div>

              <!-- 索引未就绪时的引导 -->
              <el-alert
                v-if="status && !status.index.ready"
                type="warning"
                :closable="false"
                show-icon
                style="margin-top: 20px; text-align: left"
              >
                <template #title>向量索引尚未构建，检索会返回空结果</template>
                <template #default>
                  <div style="line-height: 1.9; margin-top: 6px">
                    执行任一项即可：<br />
                    · 命令行：<code>python manage.py build_index</code><br />
                    · 或点击右侧「重建索引」按钮
                  </div>
                </template>
              </el-alert>
            </div>

            <!-- 消息气泡 -->
            <div
              v-for="(msg, index) in messages"
              :key="index"
              class="chat-message"
              :class="`chat-message--${msg.role}`"
            >
              <div class="chat-message__avatar">
                <el-icon v-if="msg.role === 'user'"><User /></el-icon>
                <el-icon v-else><MagicStick /></el-icon>
              </div>

              <div class="chat-message__body">
                <div class="chat-message__bubble">
                  <!-- 流式生成中的光标 -->
                  <span v-if="msg.role === 'assistant'" class="chat-message__text">{{
                    msg.content || (msg.streaming ? '' : '（无内容）')
                  }}</span>
                  <span v-else class="chat-message__text">{{ msg.content }}</span>
                  <span v-if="msg.streaming" class="typing-cursor">▌</span>
                </div>

                <!-- 错误提示 -->
                <el-alert
                  v-if="msg.error"
                  type="error"
                  :closable="false"
                  show-icon
                  style="margin-top: 8px"
                  :title="msg.error"
                />

                <!-- 引用来源：RAG 的可解释性体现 -->
                <div v-if="msg.sources.length" class="chat-message__sources">
                  <div class="sources-title">
                    <el-icon><Link /></el-icon>
                    参考了 {{ msg.sources.length }} 个视频
                  </div>
                  <div
                    v-for="(src, si) in msg.sources"
                    :key="src.bvid"
                    class="source-item"
                    @click="openSource(src.bvid)"
                  >
                    <span class="source-item__index">[{{ si + 1 }}]</span>
                    <span class="source-item__title text-ellipsis">{{ src.title }}</span>
                    <el-tag v-if="src.partition" size="small" effect="plain">
                      {{ src.partition }}
                    </el-tag>
                    <span class="text-muted" style="font-size: 12px">
                      {{ formatNumber(src.view_count) }} 播放
                    </span>
                    <el-tag size="small" type="info" effect="plain">
                      {{ formatPercent(src.similarity, 0, true) }}
                    </el-tag>
                  </div>
                </div>

                <!-- 元信息（仅助手消息） -->
                <div v-if="msg.role === 'assistant' && !msg.streaming" class="chat-message__meta">
                  <span>{{ formatDate(msg.time, true) }}</span>
                  <span v-if="msg.provider">· {{ msg.provider }}</span>
                  <span v-if="msg.latency">· {{ msg.latency }}ms</span>
                  <el-tag v-if="msg.fallback" size="small" type="warning" effect="plain">
                    检索式回答
                  </el-tag>
                </div>
              </div>
            </div>
          </div>

          <!-- ---- 输入区 ---- -->
          <div class="chat-input">
            <el-input
              v-model="inputText"
              type="textarea"
              :rows="2"
              resize="none"
              maxlength="500"
              show-word-limit
              placeholder="输入你的问题…（Enter 发送，Shift + Enter 换行）"
              :disabled="sending"
              @keydown.enter.exact.prevent="send"
            />

            <div class="chat-input__actions">
              <el-button
                v-if="sending"
                type="danger"
                plain
                :icon="'VideoPause'"
                @click="stopGenerating"
              >
                停止生成
              </el-button>
              <el-button
                v-else
                type="primary"
                :icon="'Promotion'"
                :disabled="!inputText.trim()"
                @click="send"
              >
                发送
              </el-button>
            </div>
          </div>
        </el-card>
      </el-col>

      <!-- ==================== 右栏：状态 + 情感分析 ==================== -->
      <el-col :xs="24" :lg="8">
        <!-- ---- RAG 链路状态 ---- -->
        <el-card shadow="never" class="card-gap">
          <template #header><span>RAG 链路状态</span></template>

          <el-descriptions v-if="status" :column="1" border size="small">
            <el-descriptions-item label="向量索引">
              <el-tag :type="status.index.ready ? 'success' : 'danger'" size="small">
                {{ status.index.ready ? '已就绪' : '未构建' }}
              </el-tag>
              <span style="margin-left: 8px">{{ status.index.count }} 条向量</span>
            </el-descriptions-item>

            <el-descriptions-item label="向量化后端">
              {{ status.index.backend }}
              <span v-if="status.index.dim" class="text-muted">
                （{{ status.index.dim }} 维）
              </span>
            </el-descriptions-item>

            <el-descriptions-item label="大模型">
              <el-tag
                :type="status.fallback ? 'warning' : 'success'"
                size="small"
              >
                {{ status.llm.provider }}
              </el-tag>
              <span v-if="status.llm.model" class="text-muted" style="margin-left: 6px">
                {{ status.llm.model }}
              </span>
            </el-descriptions-item>

            <el-descriptions-item label="可用性">
              <el-tag :type="status.ready ? 'success' : 'danger'" size="small">
                {{ status.ready ? '可以问答' : '暂不可用' }}
              </el-tag>
            </el-descriptions-item>
          </el-descriptions>

          <el-alert
            v-if="status"
            :type="status.ready && !status.fallback ? 'success' : 'info'"
            :closable="false"
            show-icon
            style="margin-top: 12px"
          >
            <template #title>{{ status.hint }}</template>
          </el-alert>

          <div style="margin-top: 12px; display: flex; gap: 8px; flex-wrap: wrap">
            <el-button
              size="small"
              type="primary"
              :icon="'Refresh'"
              :loading="building"
              @click="rebuildIndex"
            >
              重建索引
            </el-button>
            <el-button size="small" :icon="'Refresh'" @click="loadStatus">
              刷新状态
            </el-button>
            <!-- 模型提供商设置：没有 Key 时的唯一出路 -->
            <el-button
              size="small"
              type="success"
              plain
              :icon="'Setting'"
              @click="providerDialogVisible = true"
            >
              模型设置
            </el-button>
          </div>

          <div v-if="status?.index.note" class="text-muted" style="font-size: 12px; margin-top: 10px; line-height: 1.7">
            {{ status.index.note }}
          </div>
        </el-card>

        <!-- ---- 批量情感分析 ---- -->
        <el-card shadow="never">
          <template #header>
            <div class="card-header">
              <span>批量情感分析</span>
              <el-tag size="small" effect="plain">无需大模型</el-tag>
            </div>
          </template>

          <el-input
            v-model="sentimentText"
            type="textarea"
            :rows="5"
            placeholder="每行一条，例如：&#10;太强了！这期质量真的高&#10;有点失望，不如上一期&#10;打卡，先收藏慢慢看"
          />

          <div style="margin-top: 10px; display: flex; align-items: center; gap: 8px">
            <el-button
              type="primary"
              size="small"
              :icon="'MagicStick'"
              :loading="sentimentAnalyzing"
              :disabled="!sentimentLineCount || sentimentLineCount > MAX_BATCH"
              @click="analyzeSentiment"
            >
              分析（{{ sentimentLineCount }} 条）
            </el-button>
            <span class="text-muted" style="font-size: 12px">最多 {{ MAX_BATCH }} 条</span>
          </div>

          <!-- 结果 -->
          <template v-if="sentimentResults.length">
            <el-divider />

            <EChart :option="sentimentPieOption" height="200px" />

            <div class="sentiment-list">
              <div
                v-for="(r, i) in sentimentResults"
                :key="i"
                class="sentiment-item"
              >
                <div class="sentiment-item__text text-ellipsis">{{ r.text }}</div>
                <el-tag
                  size="small"
                  :type="r.label === 'positive' ? 'success' : r.label === 'negative' ? 'danger' : 'info'"
                >
                  {{ r.label_display }}
                </el-tag>
                <span
                  class="sentiment-item__score"
                  :style="{ color: sentimentColor(r.label) }"
                >
                  {{ r.score.toFixed(2) }}
                </span>
              </div>
            </div>
          </template>
        </el-card>
      </el-col>
    </el-row>

    <!-- 模型提供商设置（Key 加密保存，不会上传） -->
    <ModelProviderDialog
      v-model="providerDialogVisible"
      @changed="onProviderChanged"
    />
  </div>
</template>

<style scoped>
.card-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.chat-card :deep(.el-card__body) {
  padding: 0;
  display: flex;
  flex-direction: column;
}

/* ---------- 消息列表 ---------- */
.chat-messages {
  flex: 1;
  min-height: 480px;
  max-height: calc(100vh - 320px);
  overflow-y: auto;
  padding: 20px;
  background: #fafbfc;
}

.chat-empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  height: 100%;
  min-height: 400px;
  text-align: center;
}

.chat-empty h3 {
  margin: 16px 0 6px;
  font-size: 16px;
  color: #606266;
}

.chat-empty p {
  margin: 0;
  font-size: 13px;
  max-width: 420px;
  line-height: 1.7;
}

.example-list {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  justify-content: center;
  margin-top: 20px;
  max-width: 460px;
}

.example-tag {
  cursor: pointer;
  transition: all 0.15s ease;
}

.example-tag:hover {
  transform: translateY(-2px);
  border-color: #409eff;
  color: #409eff;
}

/* ---------- 消息气泡 ---------- */
.chat-message {
  display: flex;
  gap: 10px;
  margin-bottom: 20px;
}

.chat-message--user {
  flex-direction: row-reverse;
}

.chat-message__avatar {
  width: 32px;
  height: 32px;
  border-radius: 8px;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  background: #ecf5ff;
  color: #409eff;
}

.chat-message--user .chat-message__avatar {
  background: #f0f9eb;
  color: #67c23a;
}

.chat-message__body {
  min-width: 0;
  max-width: 82%;
}

.chat-message__bubble {
  padding: 10px 14px;
  border-radius: 10px;
  background: #ffffff;
  border: 1px solid #ebeef5;
  line-height: 1.75;
  font-size: 14px;
}

.chat-message--user .chat-message__bubble {
  background: #ecf5ff;
  border-color: #d9ecff;
}

.chat-message__text {
  white-space: pre-wrap;
  word-break: break-word;
}

/* 流式光标闪烁 */
.typing-cursor {
  display: inline-block;
  color: #409eff;
  animation: cursor-blink 0.9s steps(2, start) infinite;
}

@keyframes cursor-blink {
  to {
    visibility: hidden;
  }
}

/* ---------- 引用来源 ---------- */
.chat-message__sources {
  margin-top: 10px;
  padding: 10px 12px;
  background: #ffffff;
  border: 1px dashed #dcdfe6;
  border-radius: 8px;
}

.sources-title {
  display: flex;
  align-items: center;
  gap: 4px;
  font-size: 12px;
  color: #909399;
  margin-bottom: 8px;
}

.source-item {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 5px 0;
  font-size: 13px;
  cursor: pointer;
  border-radius: 4px;
  transition: background 0.15s ease;
}

.source-item:hover {
  background: #f5f7fa;
}

.source-item__index {
  color: #409eff;
  font-weight: 600;
  flex-shrink: 0;
}

.source-item__title {
  flex: 1;
  min-width: 0;
  color: #606266;
}

/* ---------- 元信息 ---------- */
.chat-message__meta {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-top: 6px;
  font-size: 11px;
  color: #c0c4cc;
}

/* ---------- 输入区 ---------- */
.chat-input {
  border-top: 1px solid #ebeef5;
  padding: 14px 20px 16px;
  background: #ffffff;
}

.chat-input__actions {
  display: flex;
  justify-content: flex-end;
  margin-top: 10px;
}

/* ---------- 情感分析结果 ---------- */
.sentiment-list {
  max-height: 240px;
  overflow-y: auto;
}

.sentiment-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 0;
  border-bottom: 1px solid #f5f7fa;
  font-size: 13px;
}

.sentiment-item__text {
  flex: 1;
  min-width: 0;
  color: #606266;
}

.sentiment-item__score {
  font-variant-numeric: tabular-nums;
  font-weight: 600;
  flex-shrink: 0;
}
</style>
