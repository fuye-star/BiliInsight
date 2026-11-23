/**
 * 接口定义 —— 与后端 16 个接口一一对应。
 *
 * 【为什么要集中定义而不是在页面里直接写 URL】
 *  1. 接口路径只出现一次，后端改路由时只需改这里
 *  2. 统一在这里声明泛型，页面里拿到的数据就是有类型的
 *  3. 便于统计"用了哪些接口"，写报告/答辩时可以直接列清单
 */

import { del, get, getPaginated, patch, post, postStream } from './request'

import type {
  ChatRequest,
  ChatResponse,
  ChatSessionDetail,
  ChatSessionItem,
  CrawlOptions,
  CrawlResult,
  Danmaku,
  EnrichState,
  HealthData,
  IndexBuildResult,
  InteractionData,
  ModelProviderItem,
  Overview,
  PaginatedData,
  Partition,
  PartitionRatioData,
  ProviderPayload,
  ProviderPreset,
  ProviderTestResult,
  RagStatus,
  SentimentAnalyzeData,
  SentimentData,
  TopUpusersData,
  TopVideosData,
  TrendData,
  UpUser,
  Video,
  VideoDetail,
  WordCloudData,
} from '@/types'

export { postStream }

// ===========================================================================
// 健康检查
// ===========================================================================
export const healthApi = {
  /** 探测后端与依赖（MySQL / Redis）是否可用 */
  check: () => get<HealthData>('/health/'),
}

// ===========================================================================
// 统计分析（8 个接口）
// ===========================================================================
export const analyticsApi = {
  /** 总览指标：视频数、播放总量、平均互动率等 */
  overview: () => get<Overview>('/analytics/overview/'),

  /** 播放量趋势（按天聚合） */
  trend: (params: { days?: number; partition?: string } = {}) =>
    get<TrendData>('/analytics/trend/', params),

  /** 分区占比（数量占比 + 播放占比） */
  partitionRatio: () => get<PartitionRatioData>('/analytics/partition-ratio/'),

  /** UP主排行榜 */
  topUpusers: (params: { limit?: number; order_by?: string } = {}) =>
    get<TopUpusersData>('/analytics/top-upusers/', params),

  /** 视频排行榜 */
  topVideos: (
    params: { limit?: number; order_by?: string; partition?: string } = {},
  ) => get<TopVideosData>('/analytics/top-videos/', params),

  /** 词云词频 */
  wordcloud: (
    params: { source?: 'danmaku' | 'title'; bvid?: string; limit?: number } = {},
  ) => get<WordCloudData>('/analytics/wordcloud/', params),

  /** 弹幕情感分布与情绪波动 */
  sentiment: (params: { bvid?: string; segments?: number } = {}) =>
    get<SentimentData>('/analytics/sentiment/', params),

  /** 互动质量分析（创作者选题的核心参考） */
  interaction: (params: { limit?: number } = {}) =>
    get<InteractionData>('/analytics/interaction/', params),
}

// ===========================================================================
// 视频数据（5 个接口）
// ===========================================================================
export interface VideoListParams {
  page?: number
  page_size?: number
  partition?: string
  up_mid?: number
  search?: string
  min_view?: number
  has_danmaku?: boolean
  ordering?: string
}

export const videoApi = {
  /** 视频列表（分页 / 筛选 / 搜索 / 排序） */
  list: (params: VideoListParams = {}) =>
    getPaginated<Video>('/videos/', params as Record<string, unknown>),

  /** 视频详情（按 bvid） */
  detail: (bvid: string) => get<VideoDetail>(`/videos/${bvid}/`),

  /** 某视频的弹幕（分页） */
  danmaku: (
    bvid: string,
    params: { page?: number; page_size?: number; sentiment?: string } = {},
  ) =>
    getPaginated<Danmaku>(`/videos/${bvid}/danmaku/`, params) as Promise<
      PaginatedData<Danmaku> & {
        video: { bvid: string; title: string; duration: number; duration_display: string }
      }
    >,

  /** UP主列表 */
  upusers: (params: { page?: number; page_size?: number; search?: string; ordering?: string } = {}) =>
    getPaginated<UpUser>('/upusers/', params as Record<string, unknown>),

  /** 分区列表（后端不分页，直接返回数组） */
  partitions: () => get<Partition[]>('/partitions/'),
}

// ===========================================================================
// AI 模块
// ===========================================================================
export const aiApi = {
  /** 对文本做情感分析（单条或批量） */
  analyzeSentiment: (payload: { text?: string; texts?: string[] }) =>
    post<SentimentAnalyzeData>('/ai/analyze-sentiment/', payload),

  /** 检查情感分析后端是否可用 */
  sentimentHealth: () =>
    get<{ backend: string; available: boolean; probe: unknown }>(
      '/ai/sentiment-health/',
    ),

  // ---- 阶段五：RAG 对话 ----

  /** RAG 链路状态（向量索引 + 大模型 Provider） */
  status: () => get<RagStatus>('/ai/status/'),

  /** 非流式对话（便于调试与测试；前端默认用流式） */
  chat: (payload: ChatRequest) => post<ChatResponse>('/ai/chat/', { ...payload, stream: false }),

  /** 重建向量索引 */
  buildIndex: (rebuild = true) =>
    post<IndexBuildResult>('/ai/build-index/', { rebuild }),

  /** 历史会话列表 */
  history: (limit = 20) =>
    get<{ total: number; items: ChatSessionItem[] }>('/ai/history/', { limit }),

  /** 某会话的消息记录 */
  historyDetail: (sessionId: number) =>
    get<ChatSessionDetail>(`/ai/history/${sessionId}/`),

  // ---- 大模型提供商（用户自定义 API）----

  /** 内置服务商预设（下拉框用） */
  providerPresets: () =>
    get<{ presets: ProviderPreset[]; default_type: string }>('/ai/providers/presets/'),

  /** 已保存的配置列表（Key 已打码） */
  providers: () =>
    get<{ total: number; items: ModelProviderItem[]; active_id: number | null }>(
      '/ai/providers/',
    ),

  /** 新增配置 */
  createProvider: (payload: ProviderPayload) =>
    post<ModelProviderItem>('/ai/providers/', payload),

  /** 修改配置（局部更新，Key 不传即保持不变） */
  updateProvider: (id: number, payload: ProviderPayload) =>
    patch<ModelProviderItem>(`/ai/providers/${id}/`, payload),

  /** 删除配置 */
  deleteProvider: (id: number) => del<{ deleted: number }>(`/ai/providers/${id}/`),

  /** 设为当前启用 */
  activateProvider: (id: number) =>
    post<ModelProviderItem>(`/ai/providers/${id}/activate/`, {}),

  /** 测试连通性（会发起一次极小的真实调用） */
  testProvider: (id: number) =>
    post<ProviderTestResult>(`/ai/providers/${id}/test/`, {}),
}

// ===========================================================================
// 抓取（桌面版「更新数据」按钮）
// ===========================================================================
export const spiderApi = {
  /**
   * 立即抓取一批真实数据（同步，秒级返回）。
   *
   * 默认走**全站热门**接口并自动翻页 —— 该接口风控宽松、支持翻页，
   * 每次点击都能拿到新的视频（排行榜接口每次都是同一批 Top 97，
   * 且最容易触发 -352，因此不作为默认）。
   *
   * 抓完后端会自动清统计缓存并重建检索索引，
   * 所以调用成功后重新拉一遍看板数据就能看到新内容。
   */
  crawl: (payload: { source?: 'popular' | 'partition'; partition?: string; limit?: number } = {}) =>
    post<CrawlResult>('/spider/crawl/', payload),

  /** 可抓取的分区列表与默认值 */
  options: () => get<CrawlOptions>('/spider/options/'),

  /** 启动后台补全任务（补粉丝数 + 抓弹幕） */
  enrichStart: (payload: { followers_limit?: number; danmaku_limit?: number } = {}) =>
    post<{ started: boolean }>('/spider/enrich/', payload),

  /** 查询补全进度 */
  enrichStatus: () => get<EnrichState>('/spider/enrich/'),
}
