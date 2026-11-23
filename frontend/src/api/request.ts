/**
 * Axios 封装 —— 前端与后端之间的唯一出口。
 *
 * 【为什么必须统一封装】
 * 后端的响应结构是固定的三层信封：
 *     { "code": 0, "message": "ok", "data": {...} }
 * 如果每个页面各自处理，会出现大量重复的 res.data.data 取值与错误判断。
 * 在这里统一"拆信封 + 抛异常"，业务代码只需关心 data 本身。
 *
 * 【错误处理策略】
 * 关键在于区分两类失败：
 *   1. HTTP 层失败（404 / 500 / 超时）—— axios 会 reject
 *   2. 业务层失败（HTTP 200 但 code != 0）—— axios 认为成功
 * 两者都要转成异常抛给调用方，否则业务错误会被静默忽略。
 */

import axios, {
  type AxiosInstance,
  type AxiosRequestConfig,
  type AxiosResponse,
} from 'axios'
import { ElMessage } from 'element-plus'

import type { ApiEnvelope, PaginatedData } from '@/types'

/** 后端返回的业务成功码 */
const SUCCESS_CODE = 0

/** 后端业务错误码（对应 apps/common/response.py 的 BusinessCode） */
export const BusinessCode = {
  SUCCESS: 0,
  BAD_REQUEST: 1001,
  UNAUTHORIZED: 1002,
  FORBIDDEN: 1003,
  NOT_FOUND: 1004,
  RATE_LIMITED: 1005,
  SERVER_ERROR: 1500,
} as const

/**
 * 业务异常。
 *
 * 单独定义而不是复用 Error，是为了让调用方能通过 instanceof 区分
 * "业务失败"与"网络/代码异常"，从而给出不同的 UI 反馈。
 */
export class ApiError extends Error {
  code: number
  httpStatus?: number

  constructor(message: string, code: number, httpStatus?: number) {
    super(message)
    this.name = 'ApiError'
    this.code = code
    this.httpStatus = httpStatus
  }
}

/** HTTP 状态码到中文提示的映射，避免把英文状态描述直接甩给用户 */
const HTTP_MESSAGE: Record<number, string> = {
  400: '请求参数有误',
  401: '登录状态已失效，请重新登录',
  403: '没有权限执行该操作',
  404: '请求的资源不存在',
  429: '请求过于频繁，请稍后重试',
  500: '服务器内部错误',
  502: '网关错误，请稍后重试',
  503: '服务暂时不可用',
  504: '网关超时，请稍后重试',
}

/** 创建 axios 实例 */
const http: AxiosInstance = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL || '/api',
  // 15 秒足够覆盖统计接口（含首次聚合），又不至于让用户等太久
  timeout: 15000,
  headers: {
    'Content-Type': 'application/json',
  },
})

// ---------------------------------------------------------------------------
// 请求拦截器
// ---------------------------------------------------------------------------
http.interceptors.request.use(
  (config) => {
    // 预留：后续接入 JWT 时在此附加 Authorization 头
    // const token = localStorage.getItem('access_token')
    // if (token) config.headers.Authorization = `Bearer ${token}`
    return config
  },
  (error) => Promise.reject(error),
)

// ---------------------------------------------------------------------------
// 响应拦截器
// ---------------------------------------------------------------------------
http.interceptors.response.use(
  (response: AxiosResponse<ApiEnvelope>) => {
    const payload = response.data

    // 非信封结构（例如某些第三方接口）直接返回，避免误判
    if (payload == null || typeof payload !== 'object' || !('code' in payload)) {
      return response
    }

    // 业务层失败：HTTP 是 200，但 code 不为 0
    if (payload.code !== SUCCESS_CODE) {
      throw new ApiError(payload.message || '请求失败', payload.code, response.status)
    }

    return response
  },
  (error) => {
    // ---- HTTP 层失败 ----
    let message = '网络异常，请检查后端服务是否已启动'

    if (error.response) {
      const status = error.response.status
      const detail = error.response.data

      // 优先使用后端返回的 message（我们的 handler 保证有这个字段）
      if (detail && typeof detail === 'object' && detail.message) {
        message = detail.message
      } else {
        message = HTTP_MESSAGE[status] || `请求失败（HTTP ${status}）`
      }

      return Promise.reject(
        new ApiError(message, detail?.code ?? status, status),
      )
    }

    if (error.code === 'ECONNABORTED') {
      message = '请求超时，后端可能正在处理大量数据'
    } else if (error.code === 'ERR_NETWORK') {
      message = '无法连接后端服务，请确认 8000 端口已启动'
    }

    return Promise.reject(new ApiError(message, -1))
  },
)

// ---------------------------------------------------------------------------
// 对外方法
// ---------------------------------------------------------------------------
/**
 * 发起 GET 请求并返回业务数据（已拆信封）。
 *
 * @param url    接口路径（相对于 baseURL），如 '/analytics/overview/'
 * @param params 查询参数
 * @param config 额外的 axios 配置
 * @returns      信封中的 data 字段
 */
export async function get<T = unknown>(
  url: string,
  params?: Record<string, unknown>,
  config?: AxiosRequestConfig,
): Promise<T> {
  const response = await http.get<ApiEnvelope<T>>(url, { params, ...config })
  return response.data.data
}

/**
 * 发起 POST 请求并返回业务数据。
 *
 * @param url  接口路径
 * @param body 请求体
 */
export async function post<T = unknown>(
  url: string,
  body?: unknown,
  config?: AxiosRequestConfig,
): Promise<T> {
  const response = await http.post<ApiEnvelope<T>>(url, body, config)
  return response.data.data
}

/**
 * 分页 GET：返回完整分页对象（包含 total / page 等元信息）。
 *
 * 【为什么不复用 get()】
 * get() 返回的是 data 字段内容，而分页接口的 data 本身就是分页对象。
 * 单独提供这个函数是为了让类型更明确，调用方不必手动断言。
 */
export async function getPaginated<T = unknown>(
  url: string,
  params?: Record<string, unknown>,
): Promise<PaginatedData<T>> {
  const response = await http.get<ApiEnvelope<PaginatedData<T>>>(url, { params })
  return response.data.data
}

/**
 * 发起 PATCH 请求（局部更新）。
 *
 * 【为什么需要它】
 * 「模型提供商」配置的编辑是局部更新：用户可能只改了模型名，
 * 却不能把 API Key 一起提交（后端拿到空值会当成"清空 Key"）。
 * 用 PATCH 只提交改动字段，语义最准确。
 */
export async function patch<T = unknown>(
  url: string,
  body?: unknown,
  config?: AxiosRequestConfig,
): Promise<T> {
  const response = await http.patch<ApiEnvelope<T>>(url, body, config)
  return response.data.data
}

/**
 * 发起 DELETE 请求。
 */
export async function del<T = unknown>(
  url: string,
  config?: AxiosRequestConfig,
): Promise<T> {
  const response = await http.delete<ApiEnvelope<T>>(url, config)
  return response.data.data
}

/**
 * 统一处理接口异常：弹出提示并返回兜底值。
 *
 * 【用法场景】
 * 页面的加载函数里如果每个 await 都写 try/catch 会非常啰嗦。
 * 用这个包装后，失败时自动提示，并返回兜底值让页面正常渲染空状态。
 *
 * 示例：
 *     const data = await withErrorToast(() => analyticsApi.overview(), null)
 */
export async function withErrorToast<T>(
  task: () => Promise<T>,
  fallback: T,
  options: { silent?: boolean } = {},
): Promise<T> {
  try {
    return await task()
  } catch (error) {
    const message =
      error instanceof ApiError ? error.message : '发生未知错误，请查看控制台'

    if (!options.silent) {
      ElMessage.error(message)
    }
    // 保留原始错误便于排查（不影响页面继续渲染）
    console.error('[BiliInsight] 接口调用失败：', error)

    return fallback
  }
}

/**
 * SSE 流式请求。
 *
 * 【为什么必须用 fetch 而不是 EventSource】
 * 浏览器原生的 EventSource 有两个硬限制：
 *   1. 只支持 GET，无法发送 JSON 请求体
 *   2. 无法自定义请求头
 * 而我们的对话接口需要 POST + JSON 体，因此用 fetch + ReadableStream
 * 手动解析 SSE 协议。
 *
 * 【SSE 协议格式】
 *     data: {"type":"chunk","data":"文本"}\n\n
 * 以空行分隔帧，每帧内可能有多行（本后端只用单行 data）。
 *
 * @param url    接口路径
 * @param body   请求体
 * @param onEvent 每收到一帧就回调，参数为解析后的对象
 * @param signal  AbortSignal，用于中断生成
 */
export async function postStream(
  url: string,
  body: unknown,
  onEvent: (event: Record<string, unknown>) => void,
  signal?: AbortSignal,
): Promise<void> {
  const baseURL = import.meta.env.VITE_API_BASE_URL || '/api'
  const response = await fetch(`${baseURL}${url}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
    signal,
  })

  if (!response.ok) {
    // 尝试读出后端的统一错误信息，读不到就退回状态码
    let message = `请求失败（HTTP ${response.status}）`
    try {
      const detail = await response.json()
      if (detail?.message) message = detail.message
    } catch {
      /* 响应体不是 JSON，忽略 */
    }
    throw new ApiError(message, response.status, response.status)
  }

  if (!response.body) {
    throw new ApiError('浏览器不支持流式响应', -1)
  }

  const reader = response.body.getReader()
  const decoder = new TextDecoder('utf-8')
  let buffer = ''

  // eslint-disable-next-line no-constant-condition
  while (true) {
    const { done, value } = await reader.read()
    if (done) break

    // stream: true 让多字节字符（中文）能跨 chunk 正确解码
    buffer += decoder.decode(value, { stream: true })

    // 按空行切分完整的帧；最后一段可能不完整，留在 buffer 里等下次
    const frames = buffer.split('\n\n')
    buffer = frames.pop() ?? ''

    for (const frame of frames) {
      // 一个帧可能有多行 data: ，这里全部取出后拼接
      const dataLines = frame
        .split('\n')
        .filter((line) => line.startsWith('data:'))
        .map((line) => line.slice(5).trim())

      if (!dataLines.length) continue

      try {
        onEvent(JSON.parse(dataLines.join('')))
      } catch {
        // 单帧解析失败不应中断整个流
        console.warn('[BiliInsight] 无法解析 SSE 帧：', frame)
      }
    }
  }
}

export default http
