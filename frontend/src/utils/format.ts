/**
 * 通用格式化工具。
 *
 * 集中放置的原因：数字格式化（播放量、互动率）在多个页面重复使用，
 * 分散实现容易出现"总览页显示 1234.5 万、榜单页显示 12345678"这种不一致。
 */

/**
 * 格式化大数字，超过一万时转为「万 / 亿」。
 *
 * 视频播放量动辄百万，直接显示 2592625 既长又难读。
 *
 * @param value  原始数值
 * @param digits 保留小数位，默认 1
 * @returns      如 "259.3万"、"1.2亿"
 */
export function formatNumber(value: number | null | undefined, digits = 1): string {
  if (value == null || Number.isNaN(value)) return '-'

  const abs = Math.abs(value)

  if (abs >= 1e8) {
    return `${(value / 1e8).toFixed(digits)}亿`
  }
  if (abs >= 1e4) {
    return `${(value / 1e4).toFixed(digits)}万`
  }
  // 小数值直接显示，避免出现 "523.0" 这种多余小数
  return Number.isInteger(value) ? String(value) : value.toFixed(digits)
}

/**
 * 格式化百分比。
 *
 * 注意：后端返回的 pct 字段已经是百分数（如 58.8），
 * 而 interaction_rate 是小数（如 0.0859）。
 * 用 fromRatio 参数区分两种来源，避免重复乘 100。
 *
 * @param value     数值
 * @param digits    小数位，默认 2
 * @param fromRatio 为 true 时表示入参是 0-1 的小数，需要乘 100
 */
export function formatPercent(
  value: number | null | undefined,
  digits = 2,
  fromRatio = false,
): string {
  if (value == null || Number.isNaN(value)) return '-'
  const pct = fromRatio ? value * 100 : value
  return `${pct.toFixed(digits)}%`
}

/**
 * 格式化日期时间（ISO 字符串 -> 可读中文格式）。
 *
 * @param iso      后端返回的 ISO 时间字符串
 * @param withTime 是否显示时分，默认 false
 */
export function formatDate(iso: string | null | undefined, withTime = false): string {
  if (!iso) return '-'

  const date = new Date(iso)
  if (Number.isNaN(date.getTime())) return '-'

  const y = date.getFullYear()
  const m = String(date.getMonth() + 1).padStart(2, '0')
  const d = String(date.getDate()).padStart(2, '0')

  if (!withTime) return `${y}-${m}-${d}`

  const hh = String(date.getHours()).padStart(2, '0')
  const mm = String(date.getMinutes()).padStart(2, '0')
  return `${y}-${m}-${d} ${hh}:${mm}`
}

/**
 * 把秒数格式化为 mm:ss 或 hh:mm:ss。
 *
 * 后端已提供 duration_display 字段，但弹幕时间点等场景
 * 仍需在前端自行转换（弹幕接口返回的是秒数）。
 *
 * @param seconds 秒数
 */
export function formatDuration(seconds: number | null | undefined): string {
  if (seconds == null || Number.isNaN(seconds)) return '00:00'

  const total = Math.max(0, Math.floor(seconds))
  const h = Math.floor(total / 3600)
  const m = Math.floor((total % 3600) / 60)
  const s = total % 60

  const pad = (n: number) => String(n).padStart(2, '0')

  return h > 0 ? `${pad(h)}:${pad(m)}:${pad(s)}` : `${pad(m)}:${pad(s)}`
}

/**
 * 情感标签 -> Element Plus 标签类型。
 *
 * 让"正向=绿色、负向=红色、中性=灰色"的映射只定义一次，
 * 避免各页面配色不一致。
 */
export function sentimentTagType(
  label: string,
): 'success' | 'danger' | 'info' {
  if (label === 'positive') return 'success'
  if (label === 'negative') return 'danger'
  return 'info'
}

/** 情感标签 -> 颜色（用于图表） */
export function sentimentColor(label: string): string {
  if (label === 'positive') return '#67C23A'
  if (label === 'negative') return '#F56C6C'
  return '#909399'
}

/** 情感标签 -> 中文名 */
export function sentimentText(label: string): string {
  if (label === 'positive') return '正向'
  if (label === 'negative') return '负向'
  if (label === 'neutral') return '中性'
  return '未分析'
}

/**
 * 生成互补色列表，用于图表中的多系列配色。
 *
 * 优先使用后端分区表里配置的 color（保证同一分区在各页面颜色一致），
 * 缺失时才回退到这个调色板。
 */
export const FALLBACK_COLORS = [
  '#5470C6',
  '#91CC75',
  '#FAC858',
  '#EE6666',
  '#73C0DE',
  '#3BA272',
  '#FC8452',
  '#9A60B4',
  '#EA7CCC',
  '#C4CCD3',
]

/** 按索引取颜色（超出长度时循环） */
export function pickColor(index: number): string {
  return FALLBACK_COLORS[index % FALLBACK_COLORS.length]
}
