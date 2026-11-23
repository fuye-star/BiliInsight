/**
 * ECharts 按需注册。
 *
 * 【为什么必须按需引入】
 * ECharts 完整包体积超过 1 MB（gzip 后仍约 350 KB）。
 * 本项目实际只用到折线图、柱状图、饼图、散点图与几个基础组件，
 * 按需注册后能显著减小产物体积。
 * 这是 README 中"前端性能优化"加分项的具体落点。
 *
 * 【重要】所有图表必须在调用前完成注册，否则运行时会报
 * "Component series.xxx not exists"。因此统一的入口就是这个文件。
 */

import * as echarts from 'echarts/core'

// ---- 图表类型 ----
import {
  BarChart,
  LineChart,
  PieChart,
  ScatterChart,
  type BarSeriesOption,
  type LineSeriesOption,
  type PieSeriesOption,
  type ScatterSeriesOption,
} from 'echarts/charts'

// ---- 组件 ----
import {
  DatasetComponent,
  DataZoomComponent,
  GridComponent,
  LegendComponent,
  MarkLineComponent,
  TitleComponent,
  ToolboxComponent,
  TooltipComponent,
  TransformComponent,
  type DatasetComponentOption,
  type DataZoomComponentOption,
  type GridComponentOption,
  type LegendComponentOption,
  type TitleComponentOption,
  type ToolboxComponentOption,
  type TooltipComponentOption,
} from 'echarts/components'

// ---- 渲染器 ----
import { CanvasRenderer } from 'echarts/renderers'

import type { ComposeOption } from 'echarts/core'

// ---------------------------------------------------------------------------
// 注册
// ---------------------------------------------------------------------------
echarts.use([
  // 图表
  LineChart,
  BarChart,
  PieChart,
  ScatterChart,
  // 组件
  TitleComponent,
  TooltipComponent,
  LegendComponent,
  GridComponent,
  DatasetComponent,
  TransformComponent,
  DataZoomComponent,
  ToolboxComponent,
  MarkLineComponent,
  // 渲染器
  CanvasRenderer,
])

/**
 * 组合后的 EChartsOption 类型。
 *
 * 好处：写图表配置时有类型提示，拼错组件名会在编译期报错，
 * 而不是等到运行时图表一片空白才去排查。
 */
export type EChartsOption = ComposeOption<
  | LineSeriesOption
  | BarSeriesOption
  | PieSeriesOption
  | ScatterSeriesOption
  | TitleComponentOption
  | TooltipComponentOption
  | LegendComponentOption
  | GridComponentOption
  | DatasetComponentOption
  | DataZoomComponentOption
  | ToolboxComponentOption
>

export { echarts }
