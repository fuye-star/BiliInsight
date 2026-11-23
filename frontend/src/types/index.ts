/**
 * 后端接口数据结构。
 *
 * 【为什么单独成文件而不是放在 env.d.ts】
 * env.d.ts 是**声明文件**（.d.ts），它只用于给编译器提供类型信息，
 * 不能作为模块被 import —— 写成 `import type { Video } from '@/env.d'`
 * 会解析失败。
 *
 * 因此把业务类型放在这个普通 .ts 文件里，供各模块正常导入；
 * env.d.ts 只保留"全局声明"（.vue 模块、import.meta.env）。
 *
 * 这些类型与 Django 侧的序列化器一一对应，改动时需同步两处。
 */

/** 统一响应信封（对应 apps/common/response.py） */
export interface ApiEnvelope<T = unknown> {
  code: number
  message: string
  data: T
}

/** 分页响应（对应 apps/common/pagination.py） */
export interface PaginatedData<T> {
  total: number
  page: number
  page_size: number
  total_pages: number
  has_next: boolean
  has_previous: boolean
  results: T[]
}

/** 视频（列表项，对应 VideoListSerializer） */
export interface Video {
  id: number
  bvid: string
  aid: number | null
  title: string
  cover_url: string
  duration: number
  duration_display: string
  pubdate: string | null
  partition: string | null
  partition_color: string
  up_name: string | null
  up_mid: number | null
  up_avatar: string
  tags: string
  tag_list: string[]
  view_count: number
  like_count: number
  coin_count: number
  favorite_count: number
  share_count: number
  danmaku_count: number
  reply_count: number
  interaction_rate: number
  /** 是否为模拟数据（bvid 为虚构值，B站无法访问） */
  is_demo: boolean
  /** 数据来源：real（真实抓取）/ demo（模拟数据） */
  data_source: 'real' | 'demo'
  /** B站原站地址（模拟数据点了会 404） */
  source_url: string
}

/** 视频详情（比列表项多简介与本地弹幕数） */
export interface VideoDetail extends Video {
  description: string
  local_danmaku_count: number
  created_at: string
  updated_at: string
}

/** 情感标签取值 */
export type SentimentLabel = 'positive' | 'neutral' | 'negative' | ''

/** 弹幕 */
export interface Danmaku {
  id: number
  dmid: number | null
  content: string
  video_time: number
  send_time: string | null
  sentiment_score: number | null
  sentiment_label: SentimentLabel
  sentiment_label_display: string
  emotion_tags: string
  emotion_tag_list: string[]
}

/** 分区 */
export interface Partition {
  id: number
  name: string
  bili_tid: number | null
  color: string
  video_count: number
}

/** UP主 */
export interface UpUser {
  id?: number
  mid: number
  name: string
  avatar: string
  sign?: string
  follower_count: number
  video_count: number
}

/** 总览统计 */
export interface Overview {
  video_count: number
  /** 真实抓取入库的视频数（is_demo=False） */
  real_videos: number
  /** seed_demo 生成的模拟视频数（is_demo=True） */
  demo_videos: number
  /** 真实数据占比，0-1 */
  real_ratio: number
  upuser_count: number
  partition_count: number
  danmaku_count: number
  total_view: number
  total_like: number
  total_coin: number
  total_favorite: number
  total_danmaku: number
  avg_view: number
  avg_interaction_rate: number
  latest_pubdate: string | null
}

/** 趋势数据点 */
export interface TrendPoint {
  date: string
  video_count: number
  view_sum: number
  like_sum: number
  avg_view: number
}

export interface TrendData {
  days: number
  partition: string
  points: TrendPoint[]
}

/** 分区占比项 */
export interface PartitionRatioItem {
  name: string
  bili_tid: number | null
  color: string
  video_count: number
  view_sum: number
  like_sum: number
  avg_view: number
  video_pct: number
  view_pct: number
}

export interface PartitionRatioData {
  total_videos: number
  total_views: number
  items: PartitionRatioItem[]
}

/** UP主排行项 */
export interface TopUpuserItem {
  mid: number
  name: string
  avatar: string
  follower_count: number
  video_count: number
  view_sum: number
  like_sum: number
  avg_view: number
  max_view: number
}

export interface TopUpusersData {
  order_by: string
  items: TopUpuserItem[]
}

/** 视频排行项（比列表项精简） */
export interface TopVideoItem {
  bvid: string
  title: string
  cover_url: string
  duration: number
  duration_display: string
  pubdate: string | null
  partition: string | null
  up_name: string | null
  up_mid: number | null
  view_count: number
  like_count: number
  coin_count: number
  favorite_count: number
  danmaku_count: number
  interaction_rate: number
  is_demo: boolean
  data_source: 'real' | 'demo'
  source_url: string
}

export interface TopVideosData {
  order_by: string
  partition: string
  items: TopVideoItem[]
}

/** 词云项 */
export interface WordCloudItem {
  name: string
  value: number
  weight: number
}

export interface WordCloudData {
  source: string
  bvid: string
  total_words: number
  unique_words: number
  items: WordCloudItem[]
}

/** 情感分布项 */
export interface SentimentDistributionItem {
  label: 'positive' | 'neutral' | 'negative'
  name: string
  count: number
  pct: number
}

/** 情绪波动曲线点 */
export interface SentimentCurvePoint {
  segment: number
  label: string
  avg_score: number | null
  count: number
}

/** 情感统计 */
export interface SentimentData {
  bvid: string
  total: number
  analyzed: number
  distribution: SentimentDistributionItem[]
  emotion_tags: { name: string; value: number }[]
  curve: SentimentCurvePoint[]
  score_histogram: { range: string; count: number }[]
}

/** 互动质量分析项 */
export interface InteractionItem {
  bvid: string
  title: string
  partition: string | null
  up_name: string | null
  view_count: number
  interaction_rate: number
  like_count: number
  coin_count: number
  favorite_count: number
  is_demo: boolean
  source_url: string
}

export interface PartitionInteractionItem {
  name: string
  color: string
  video_count: number
  avg_interaction: number
  avg_view: number
}

export interface InteractionData {
  top_interaction: InteractionItem[]
  partition_interaction: PartitionInteractionItem[]
  high_quality_threshold: number
  high_quality_count: number
}

/** 健康检查 */
export interface HealthData {
  status: string
  services: Record<
    string,
    { ok: boolean; detail: string; latency_ms: number }
  >
  version: string
}

/** 情感分析接口返回 */
export interface SentimentAnalyzeResult {
  score: number
  label: 'positive' | 'neutral' | 'negative'
  label_display: string
  emotion_tags: string[]
  text?: string
}

export interface SentimentAnalyzeData extends SentimentAnalyzeResult {
  backend: string
  count?: number
  results?: SentimentAnalyzeResult[]
}

// ===========================================================================
// 阶段五：RAG 对话
// ===========================================================================

/** 检索命中的视频（RAG 引用来源） */
export interface RagSource {
  bvid: string
  title: string
  partition: string
  up_name: string
  view_count: number
  like_count: number
  interaction_rate: number
  duration: number
  /** 余弦相似度，越大越相关 */
  similarity: number
  /** 用于向量化的拼接文本（调试用） */
  document?: string
}

/** 向量索引状态 */
export interface IndexStatus {
  ready: boolean
  count: number
  backend: string
  available: boolean
  dim: number | null
  model?: string
  corpus_size?: number
  fitted?: boolean
  note?: string
}

/** 大模型 Provider 状态 */
export interface LlmStatus {
  provider: string
  available: boolean
  model?: string
  /** 配置来源：database（界面里配的）/ settings（环境变量）/ none（未配置） */
  source?: 'database' | 'settings' | 'none'
  /** 已保存的模型配置数量 */
  provider_count?: number
  /** 当前启用的配置名称 */
  config_name?: string
  config_id?: number
}

/** RAG 链路整体状态 */
export interface RagStatus {
  index: IndexStatus
  llm: LlmStatus
  ready: boolean
  fallback: boolean
  hint: string
}

/** 对话请求参数 */
export interface ChatRequest {
  query: string
  session_id?: number | null
  top_k?: number
  partition?: string
  stream?: boolean
  save?: boolean
}

/** 非流式对话的返回数据 */
export interface ChatResponse {
  answer: string
  sources: RagSource[]
  provider: string
  intent: string
  retrieved: number
  latency_ms: number
  fallback: boolean
  session_id: number | null
}

/** SSE 事件类型 */
export type ChatStreamEvent =
  | {
      type: 'meta'
      data: {
        intent: string
        provider: string
        fallback: boolean
        sources: RagSource[]
        retrieved: number
      }
    }
  | { type: 'chunk'; data: string }
  | {
      type: 'done'
      data: {
        answer: string
        provider: string
        latency_ms: number
        sources?: RagSource[]
      }
    }
  | { type: 'error'; data: string }

/** 会话列表项 */
export interface ChatSessionItem {
  id: number
  title: string
  provider: string
  message_count: number
  created_at: string
  updated_at: string
}

/** 会话消息 */
export interface ChatHistoryMessage {
  id: number
  role: 'user' | 'assistant' | 'system'
  content: string
  sources: string[]
  model_name: string
  latency_ms: number
  created_at: string
}

/** 会话详情 */
export interface ChatSessionDetail {
  id: number
  title: string
  provider: string
  messages: ChatHistoryMessage[]
}

/** 索引构建结果 */
export interface IndexBuildResult {
  indexed: number
  backend: string
  dim: number
  elapsed: number
  rebuild: boolean
}

// ---------------------------------------------------------------------------
// 抓取（桌面版「更新数据」）
// ---------------------------------------------------------------------------

/** 一次抓取的统计结果 */
export interface CrawlResult {
  /** 抓取来源：全站热门 / 指定分区 */
  source: 'popular' | 'partition'
  /** 实际抓取的分区（source=popular 时为空） */
  partition: string
  /** 接口解析出的条数 */
  fetched: number
  /** 新入库 */
  created: number
  /** 更新已有 */
  updated: number
  /** 失败条数 */
  failed: number
  /** 实际发出的 HTTP 请求次数 */
  requests: number
  /** 耗时（秒） */
  elapsed: number
  /** 清理掉的统计缓存键数 */
  cleared_cache: number
  /** 库内视频总数 */
  video_total: number
  /** 抓完后向量索引条数 */
  index_count: number
  /** 本次读了几页热门榜 */
  pages_read: number
  /** 下次从第几页开始（翻页游标） */
  next_page: number | null
}

/** 后台补全任务的状态 */
export interface EnrichState {
  running: boolean
  /** 可直接展示给用户的进度文案 */
  message: string
  stage: string
  total: number
  done: number
  followers: number
  danmaku: number
  error: string
}

/** 可抓取的分区选项 */
export interface CrawlOptions {
  partitions: { name: string; tid: number }[]
  default_partition: string
  default_limit: number
}

// ---------------------------------------------------------------------------
// 大模型提供商（用户自定义 API）
// ---------------------------------------------------------------------------

/** 内置的服务商预设 */
export interface ProviderPreset {
  provider_type: string
  label: string
  /** 默认接口地址（通义千问为空，因为它走官方 SDK） */
  base_url: string
  model: string
  /** 是否需要 API Key（本地 Ollama 不需要） */
  needs_key: boolean
  hint: string
  /** 申请 Key 的页面，便于用户直达 */
  key_url: string
}

/** 已保存的大模型配置（**Key 只会是打码值**） */
export interface ModelProviderItem {
  id: number
  name: string
  provider_type: string
  provider_label: string
  base_url: string
  effective_base_url: string
  model: string
  effective_model: string
  /** 形如 sk-8****cdef，用于回显；提交时原样传回表示"不修改" */
  api_key_masked: string
  has_key: boolean
  is_active: boolean
  last_test_ok: boolean | null
  last_test_at: string | null
  last_test_message: string
  created_at: string | null
}

/** 连接测试结果 */
export interface ProviderTestResult {
  ok: boolean
  message: string
  latency_ms: number
}

/** 提交给后端的配置表单 */
export interface ProviderPayload {
  name?: string
  provider_type?: string
  base_url?: string
  model?: string
  /** 留空或传打码值表示"不修改已有 Key" */
  api_key?: string
  is_active?: boolean
}
