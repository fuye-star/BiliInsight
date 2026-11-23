/**
 * ECharts 配置生成器。
 *
 * 【为什么把图表配置抽出来】
 *  1. 配置是纯数据，抽出来后可以单独测试与复用（如同一份趋势数据
 *     既画折线图也画柱状图）
 *  2. 视图组件只负责"取数据 + 传配置"，代码量大幅减少
 *  3. 统一的配色、字号、tooltip 格式只定义一次
 */

import { formatNumber } from './format'

import type { EChartsOption } from './echarts'
import type {
  PartitionInteractionItem,
  PartitionRatioItem,
  SentimentCurvePoint,
  SentimentDistributionItem,
  TrendPoint,
  WordCloudItem,
} from '@/types'

// ---------------------------------------------------------------------------
// 公共样式片段
// ---------------------------------------------------------------------------
/** 统一的文本样式 */
const AXIS_LABEL = { color: '#909399', fontSize: 12 }

/** 统一的坐标轴样式 */
const AXIS_LINE = { lineStyle: { color: '#e4e7ed' } }

/** 统一的 grid 边距（留出空间给轴标签） */
const GRID = { left: 12, right: 20, top: 40, bottom: 8, containLabel: true }

// ===========================================================================
// 1. 播放量趋势（双 Y 轴折线 + 柱状）
// ===========================================================================
/**
 * 构造趋势图配置。
 *
 * 【为什么用双 Y 轴】
 * 视频数（个位到十位）与播放量（百万级）量级差距太大，
 * 共用一根 Y 轴会让视频数的折线贴着底部看不见。
 * 左轴给播放量，右轴给视频数。
 *
 * @param points 趋势数据点
 */
export function buildTrendOption(points: TrendPoint[]): EChartsOption {
  const dates = points.map((p) => p.date)
  const views = points.map((p) => p.view_sum)
  const counts = points.map((p) => p.video_count)

  return {
    tooltip: {
      trigger: 'axis',
      axisPointer: { type: 'cross' },
      formatter: (params: unknown) => {
        // params 是数组，逐项拼装更易读的提示内容
        const list = params as { axisValue: string; seriesName: string; value: number }[]
        if (!list?.length) return ''
        const date = list[0].axisValue
        const lines = list.map((p) => {
          const val =
            p.seriesName === '播放量' ? formatNumber(p.value) : String(p.value)
          return `${p.seriesName}：${val}`
        })
        return `<b>${date}</b><br/>${lines.join('<br/>')}`
      },
    },
    legend: {
      data: ['播放量', '视频数'],
      top: 0,
      textStyle: AXIS_LABEL,
    },
    grid: GRID,
    xAxis: {
      type: 'category',
      data: dates,
      boundaryGap: true,
      axisLabel: {
        ...AXIS_LABEL,
        // 日期较长，旋转避免重叠
        rotate: 0,
        formatter: (value: string) => value.slice(5), // 只显示 MM-DD
      },
      axisLine: AXIS_LINE,
      axisTick: { show: false },
    },
    yAxis: [
      {
        type: 'value',
        name: '播放量',
        nameTextStyle: AXIS_LABEL,
        axisLabel: {
          ...AXIS_LABEL,
          formatter: (value: number) => formatNumber(value, 0),
        },
        splitLine: { lineStyle: { color: '#f0f2f5' } },
      },
      {
        type: 'value',
        name: '视频数',
        nameTextStyle: AXIS_LABEL,
        axisLabel: AXIS_LABEL,
        splitLine: { show: false },
      },
    ],
    series: [
      {
        name: '播放量',
        type: 'line',
        yAxisIndex: 0,
        data: views,
        smooth: true,
        symbol: 'circle',
        symbolSize: 6,
        itemStyle: { color: '#409eff' },
        lineStyle: { width: 2 },
        // 面积渐变让趋势更直观
        areaStyle: {
          color: {
            type: 'linear',
            x: 0,
            y: 0,
            x2: 0,
            y2: 1,
            colorStops: [
              { offset: 0, color: 'rgba(64,158,255,0.28)' },
              { offset: 1, color: 'rgba(64,158,255,0.02)' },
            ],
          },
        },
      },
      {
        name: '视频数',
        type: 'bar',
        yAxisIndex: 1,
        data: counts,
        barMaxWidth: 18,
        itemStyle: { color: '#91CC75', borderRadius: [3, 3, 0, 0] },
      },
    ],
  }
}

// ===========================================================================
// 2. 分区占比（饼图）
// ===========================================================================
/**
 * 构造分区占比饼图。
 *
 * @param items  分区数据
 * @param metric 统计维度：按视频数 或 按播放量
 */
export function buildPartitionPieOption(
  items: PartitionRatioItem[],
  metric: 'video' | 'view' = 'view',
): EChartsOption {
  const data = items.map((item) => ({
    // 图例显示"名称 + 占比"，比单纯名称信息量更大
    name: item.name,
    value: metric === 'video' ? item.video_count : item.view_sum,
    // 使用后端配置的分区色，保证与其它图表一致
    itemStyle: { color: item.color || undefined },
  }))

  return {
    tooltip: {
      trigger: 'item',
      formatter: (params: unknown) => {
        const p = params as { name: string; value: number; percent: number }
        const val = metric === 'video' ? `${p.value} 个` : formatNumber(p.value)
        return `<b>${p.name}</b><br/>${metric === 'video' ? '视频数' : '播放量'}：${val}<br/>占比：${p.percent}%`
      },
    },
    legend: {
      type: 'scroll',
      orient: 'vertical',
      right: 8,
      top: 'center',
      textStyle: AXIS_LABEL,
      // 图例项较多时限制高度，超出可滚动
      height: 260,
    },
    series: [
      {
        type: 'pie',
        // 环形图（甜甜圈）：中心留白可放总数，比实心饼图更清爽
        radius: ['42%', '68%'],
        center: ['38%', '50%'],
        avoidLabelOverlap: true,
        itemStyle: {
          borderColor: '#fff',
          borderWidth: 2,
        },
        label: {
          show: true,
          formatter: '{b}\n{d}%',
          fontSize: 12,
          color: '#606266',
        },
        labelLine: { length: 10, length2: 8 },
        emphasis: {
          label: { fontSize: 13, fontWeight: 'bold' },
          scaleSize: 6,
        },
        data,
      },
    ],
  }
}

// ===========================================================================
// 3. UP主排行（横向柱状图）
// ===========================================================================
/**
 * 构造 UP主 排行横向柱状图。
 *
 * 【为什么用横向而不是纵向】
 * UP主 昵称较长（4-8 个汉字），纵向柱状图的 X 轴标签会严重重叠。
 * 横向柱状图的标签在左侧，天然容纳长文本。
 *
 * @param names  UP主 名称
 * @param values 对应数值
 * @param metric 指标名（用于 tooltip）
 */
export function buildUpuserBarOption(
  names: string[],
  values: number[],
  metric = '总播放量',
): EChartsOption {
  // 横向柱状图从下往上绘制，因此需要反转顺序让最大值在最上面
  const reversedNames = [...names].reverse()
  const reversedValues = [...values].reverse()

  return {
    tooltip: {
      trigger: 'axis',
      axisPointer: { type: 'shadow' },
      formatter: (params: unknown) => {
        const list = params as { name: string; value: number }[]
        if (!list?.length) return ''
        return `<b>${list[0].name}</b><br/>${metric}：${formatNumber(list[0].value)}`
      },
    },
    grid: { left: 8, right: 60, top: 16, bottom: 8, containLabel: true },
    xAxis: {
      type: 'value',
      axisLabel: {
        ...AXIS_LABEL,
        formatter: (value: number) => formatNumber(value, 0),
      },
      splitLine: { lineStyle: { color: '#f0f2f5' } },
    },
    yAxis: {
      type: 'category',
      data: reversedNames,
      axisLabel: { ...AXIS_LABEL, fontSize: 12 },
      axisLine: AXIS_LINE,
      axisTick: { show: false },
    },
    series: [
      {
        type: 'bar',
        data: reversedValues,
        barMaxWidth: 16,
        itemStyle: {
          borderRadius: [0, 4, 4, 0],
          color: {
            type: 'linear',
            x: 0,
            y: 0,
            x2: 1,
            y2: 0,
            colorStops: [
              { offset: 0, color: '#79bbff' },
              { offset: 1, color: '#409eff' },
            ],
          },
        },
        // 在柱子末端直接显示数值，省得悬浮查看
        label: {
          show: true,
          position: 'right',
          fontSize: 11,
          color: '#909399',
          formatter: (params: unknown) => {
            const p = params as { value: number }
            return formatNumber(p.value, 1)
          },
        },
      },
    ],
  }
}

// ===========================================================================
// 4. 词云（用散点图模拟）
// ===========================================================================
/**
 * 构造词云图。
 *
 * 【为什么不用 echarts-wordcloud 插件】
 * 该插件需要额外安装依赖，且与本项目"减少依赖、降低答辩现场风险"的
 * 原则不符。这里用散点图 + 自定义标签模拟词云效果：
 *   · 每个词是一个散点，坐标用确定性算法打散（保证刷新后布局稳定）
 *   · 标签字号按 weight 映射
 * 效果接近词云，且零额外依赖、可交互（悬浮显示词频）。
 *
 * @param items 词频数据（weight 已归一化到 0-100）
 */
export function buildWordCloudOption(items: WordCloudItem[]): EChartsOption {
  if (!items.length) {
    return { series: [] }
  }

  // 用黄金角螺旋算法打散坐标。
  // 相比随机坐标，螺旋分布更均匀且**可复现**（同一份数据每次布局一致），
  // 否则用户每次刷新看到的词位置都不同，观感很差。
  const goldenAngle = Math.PI * (3 - Math.sqrt(5))

  const data = items.map((item, index) => {
    const radius = 4 * Math.sqrt(index)
    const theta = index * goldenAngle
    return {
      name: item.name,
      value: [
        Math.cos(theta) * radius * 3.2,
        Math.sin(theta) * radius * 2.0,
        item.value,
      ],
      // 把权重带到数据项上，供 label 的 formatter 读取
      weight: item.weight,
      itemStyle: {
        color: `hsl(${(index * 37) % 360}, 62%, 58%)`,
      },
    }
  })

  return {
    tooltip: {
      trigger: 'item',
      formatter: (params: unknown) => {
        const p = params as { name: string; value: number[] }
        return `<b>${p.name}</b><br/>出现 ${p.value[2]} 次`
      },
    },
    grid: { left: 0, right: 0, top: 0, bottom: 0 },
    xAxis: { show: false, type: 'value', min: -60, max: 60 },
    yAxis: { show: false, type: 'value', min: -40, max: 40 },
    series: [
      {
        type: 'scatter',
        data,
        symbolSize: 8,
        // 隐藏散点本身，只显示文字标签，视觉上就是词云
        itemStyle: { opacity: 0 },
        label: {
          show: true,
          formatter: (params: unknown) => {
            const p = params as { name: string; weight: number }
            return p.name
          },
          fontSize: 12,
          color: '#303133',
        },
        emphasis: {
          label: { fontWeight: 'bold', fontSize: 15 },
          itemStyle: { opacity: 1, color: '#409eff' },
        },
      },
    ],
  }
}

// ===========================================================================
// 5. 情感分布（环形图）
// ===========================================================================
/**
 * 构造情感分布环形图。
 *
 * @param distribution 情感分布数据
 */
export function buildSentimentPieOption(
  distribution: SentimentDistributionItem[],
): EChartsOption {
  // 固定配色：正向绿、负向红、中性灰，与页面标签颜色保持一致
  const colorMap: Record<string, string> = {
    positive: '#67C23A',
    neutral: '#909399',
    negative: '#F56C6C',
  }

  const data = distribution.map((item) => ({
    name: item.name,
    value: item.count,
    itemStyle: { color: colorMap[item.label] },
  }))

  return {
    tooltip: {
      trigger: 'item',
      formatter: (params: unknown) => {
        const p = params as { name: string; value: number; percent: number }
        return `<b>${p.name}</b><br/>${p.value} 条<br/>占比：${p.percent}%`
      },
    },
    legend: {
      bottom: 0,
      textStyle: AXIS_LABEL,
    },
    series: [
      {
        type: 'pie',
        radius: ['48%', '70%'],
        center: ['50%', '45%'],
        itemStyle: { borderColor: '#fff', borderWidth: 2 },
        label: {
          show: true,
          formatter: '{b}\n{d}%',
          fontSize: 12,
          color: '#606266',
        },
        labelLine: { length: 8, length2: 8 },
        data,
      },
    ],
  }
}

// ===========================================================================
// 6. 情绪波动曲线
// ===========================================================================
/**
 * 构造情绪波动折线图。
 *
 * 【为什么 Y 轴要固定 0-1 范围】
 * 情感分值本身就在 [0,1] 区间，若让 ECharts 自动缩放，
 * 一条基本平稳的曲线会被放大成剧烈波动，造成误读。
 * 固定范围并画出 0.5 中性参考线，才能正确传达"情绪是否稳定"。
 *
 * @param curve 波动曲线数据（可能含 null，表示该区间无弹幕）
 */
export function buildSentimentCurveOption(
  curve: SentimentCurvePoint[],
): EChartsOption {
  const labels = curve.map((p) => p.label)
  const scores = curve.map((p) => p.avg_score)
  const counts = curve.map((p) => p.count)

  return {
    tooltip: {
      trigger: 'axis',
      formatter: (params: unknown) => {
        const list = params as { axisValue: string; seriesName: string; value: number | null }[]
        if (!list?.length) return ''
        const label = list[0].axisValue
        const scoreItem = list.find((p) => p.seriesName === '平均情感分值')
        const countItem = list.find((p) => p.seriesName === '弹幕数')
        const scoreText =
          scoreItem?.value == null ? '无弹幕' : scoreItem.value.toFixed(3)
        return (
          `<b>进度 ${label}</b><br/>` +
          `平均情感分值：${scoreText}<br/>` +
          `弹幕数：${countItem?.value ?? 0} 条`
        )
      },
    },
    legend: {
      data: ['平均情感分值', '弹幕数'],
      top: 0,
      textStyle: AXIS_LABEL,
    },
    grid: GRID,
    xAxis: {
      type: 'category',
      data: labels,
      axisLabel: { ...AXIS_LABEL, fontSize: 11, rotate: 30 },
      axisLine: AXIS_LINE,
      axisTick: { show: false },
    },
    yAxis: [
      {
        type: 'value',
        name: '情感分值',
        min: 0,
        max: 1,
        nameTextStyle: AXIS_LABEL,
        axisLabel: {
          ...AXIS_LABEL,
          formatter: (value: number) => value.toFixed(1),
        },
        splitLine: { lineStyle: { color: '#f0f2f5' } },
      },
      {
        type: 'value',
        name: '弹幕数',
        nameTextStyle: AXIS_LABEL,
        axisLabel: AXIS_LABEL,
        splitLine: { show: false },
      },
    ],
    series: [
      {
        name: '平均情感分值',
        type: 'line',
        yAxisIndex: 0,
        data: scores,
        smooth: true,
        connectNulls: false, // 无弹幕的区间断开，不臆造数据
        symbol: 'circle',
        symbolSize: 7,
        itemStyle: { color: '#409eff' },
        lineStyle: { width: 2.5 },
        areaStyle: {
          color: {
            type: 'linear',
            x: 0, y: 0, x2: 0, y2: 1,
            colorStops: [
              { offset: 0, color: 'rgba(64,158,255,0.25)' },
              { offset: 1, color: 'rgba(64,158,255,0.02)' },
            ],
          },
        },
        // 0.5 中性参考线：让观众一眼看出曲线在中性线上方还是下方
        markLine: {
          silent: true,
          symbol: 'none',
          lineStyle: { color: '#E6A23C', type: 'dashed', width: 1 },
          data: [{ yAxis: 0.5, label: { formatter: '中性 0.5', fontSize: 11 } }],
        },
      },
      {
        name: '弹幕数',
        type: 'bar',
        yAxisIndex: 1,
        data: counts,
        barMaxWidth: 14,
        itemStyle: { color: 'rgba(144,147,153,0.35)', borderRadius: [3, 3, 0, 0] },
      },
    ],
  }
}

// ===========================================================================
// 7. 分区互动率对比（柱状图）
// ===========================================================================
/**
 * 构造分区平均互动率对比图。
 *
 * 【这个图回答什么业务问题】
 * "内容质量"比"流量"更重要。互动率（点赞+投币+收藏 / 播放）反映观众
 * 的真实认可度，按分区对比可以指导创作者"做哪个方向更容易获得认可"。
 *
 * @param items 分区互动数据
 */
export function buildPartitionInteractionOption(
  items: PartitionInteractionItem[],
): EChartsOption {
  const names = items.map((i) => i.name)
  const rates = items.map((i) => Number((i.avg_interaction * 100).toFixed(2)))
  const colors = items.map((i) => i.color || '#409eff')

  return {
    tooltip: {
      trigger: 'axis',
      axisPointer: { type: 'shadow' },
      formatter: (params: unknown) => {
        const list = params as { name: string; value: number }[]
        if (!list?.length) return ''
        const item = items.find((i) => i.name === list[0].name)
        return (
          `<b>${list[0].name}</b><br/>` +
          `平均互动率：${list[0].value}%<br/>` +
          `视频数：${item?.video_count ?? '-'}<br/>` +
          `篇均播放：${formatNumber(item?.avg_view ?? 0)}`
        )
      },
    },
    grid: { left: 8, right: 20, top: 24, bottom: 8, containLabel: true },
    xAxis: {
      type: 'category',
      data: names,
      axisLabel: { ...AXIS_LABEL, fontSize: 12 },
      axisLine: AXIS_LINE,
      axisTick: { show: false },
    },
    yAxis: {
      type: 'value',
      name: '互动率(%)',
      nameTextStyle: AXIS_LABEL,
      axisLabel: { ...AXIS_LABEL, formatter: '{value}%' },
      splitLine: { lineStyle: { color: '#f0f2f5' } },
    },
    series: [
      {
        type: 'bar',
        data: rates.map((value, index) => ({
          value,
          itemStyle: { color: colors[index], borderRadius: [4, 4, 0, 0] },
        })),
        barMaxWidth: 40,
        label: {
          show: true,
          position: 'top',
          fontSize: 11,
          color: '#606266',
          formatter: '{c}%',
        },
      },
    ],
  }
}

// ===========================================================================
// 8. 情感分值直方图
// ===========================================================================
/**
 * 构造情感分值直方图。
 *
 * 用途：观察分值分布是"两头集中"（情感表达强烈）还是"中间集中"
 * （观众态度温和），比单一的平均分更有信息量。
 *
 * @param histogram 10 个区间的计数
 */
export function buildScoreHistogramOption(
  histogram: { range: string; count: number }[],
): EChartsOption {
  const ranges = histogram.map((h) => h.range)
  const counts = histogram.map((h) => h.count)

  return {
    tooltip: {
      trigger: 'axis',
      axisPointer: { type: 'shadow' },
      formatter: (params: unknown) => {
        const list = params as { name: string; value: number }[]
        if (!list?.length) return ''
        return `分值区间 ${list[0].name}<br/>弹幕数：${list[0].value} 条`
      },
    },
    grid: { left: 8, right: 20, top: 24, bottom: 8, containLabel: true },
    xAxis: {
      type: 'category',
      data: ranges,
      axisLabel: { ...AXIS_LABEL, fontSize: 11, rotate: 30 },
      axisLine: AXIS_LINE,
      axisTick: { show: false },
    },
    yAxis: {
      type: 'value',
      name: '弹幕数',
      nameTextStyle: AXIS_LABEL,
      axisLabel: AXIS_LABEL,
      splitLine: { lineStyle: { color: '#f0f2f5' } },
    },
    series: [
      {
        type: 'bar',
        data: counts.map((value, index) => ({
          value,
          // 左端偏红、右端偏绿，直观体现"越右越正面"
          itemStyle: {
            color:
              index < 3
                ? '#F56C6C'
                : index < 5
                  ? '#E6A23C'
                  : index < 8
                    ? '#95D475'
                    : '#67C23A',
            borderRadius: [3, 3, 0, 0],
          },
        })),
        barMaxWidth: 36,
      },
    ],
  }
}
