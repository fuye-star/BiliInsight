<script setup lang="ts">
/**
 * ECharts 通用封装组件。
 *
 * 【为什么要封装】
 * 直接使用 ECharts 需要手动处理四件事，每个图表都写一遍很啰嗦：
 *   1. 实例的创建与销毁（不销毁会内存泄漏，页面切来切去会越来越卡）
 *   2. 容器尺寸变化时调用 resize（侧边栏折叠、窗口缩放都要响应）
 *   3. 数据更新时更新配置（而不是重建实例，重建会丢失动画与状态）
 *   4. loading 与空数据状态
 *
 * 封装后页面里只需：
 *     <EChart :option="option" :loading="loading" height="320px" />
 */
import { computed, onBeforeUnmount, onMounted, ref, shallowRef, watch } from 'vue'

import { echarts, type EChartsOption } from '@/utils/echarts'

const props = withDefaults(
  defineProps<{
    /** ECharts 配置项 */
    option: EChartsOption
    /** 是否加载中 */
    loading?: boolean
    /** 容器高度，如 '320px' */
    height?: string
    /** 是否显示空数据占位（由父组件根据数据判断后传入） */
    empty?: boolean
    /** 空数据文案 */
    emptyText?: string
  }>(),
  {
    loading: false,
    height: '320px',
    empty: false,
    emptyText: '暂无数据',
  },
)

const containerRef = ref<HTMLDivElement | null>(null)

/**
 * 用 shallowRef 而不是 ref 保存实例。
 *
 * 【为什么很重要】
 * ref 会把对象深度响应式化，ECharts 实例内部有大量循环引用与 DOM 节点，
 * 深度代理会造成严重的性能问题甚至卡死。shallowRef 只跟踪引用本身，
 * 是官方推荐的做法。
 */
const chart = shallowRef<echarts.ECharts | null>(null)

/** 尺寸观察器：容器宽高变化时自动 resize */
let resizeObserver: ResizeObserver | null = null

/** 容器样式 */
const containerStyle = computed(() => ({
  height: props.height,
}))

/** 同步 loading 状态到图表 */
function updateLoading() {
  if (!chart.value) return
  if (props.loading) {
    chart.value.showLoading({
      text: '加载中',
      color: '#409eff',
      textColor: '#909399',
      maskColor: 'rgba(255, 255, 255, 0.85)',
      fontSize: 13,
    })
  } else {
    chart.value.hideLoading()
  }
}

/** 初始化图表实例 */
function initChart() {
  if (!containerRef.value) return

  chart.value = echarts.init(containerRef.value, undefined, {
    // 使用 canvas 渲染（比 svg 更适合大数据量的折线图）
    renderer: 'canvas',
  })

  chart.value.setOption(props.option)
  updateLoading()

  // 监听容器尺寸变化。
  // 【为什么不用 window.resize】
  // 侧边栏折叠、父容器 flex 变化等场景不会触发 window.resize，
  // ResizeObserver 能精确捕捉元素自身尺寸变化。
  if (typeof ResizeObserver !== 'undefined') {
    resizeObserver = new ResizeObserver(() => {
      chart.value?.resize()
    })
    resizeObserver.observe(containerRef.value)
  }
}

onMounted(() => {
  initChart()
})

onBeforeUnmount(() => {
  // 【必须清理】否则组件销毁后实例仍持有 DOM 与定时器，造成内存泄漏
  resizeObserver?.disconnect()
  resizeObserver = null
  chart.value?.dispose()
  chart.value = null
})

// 配置变化时更新图表（notMerge = false 保留动画过渡）
watch(
  () => props.option,
  (newOption) => {
    if (!chart.value) return
    chart.value.setOption(newOption, { notMerge: false })
  },
  { deep: true },
)

watch(
  () => props.loading,
  () => updateLoading(),
)

/**
 * 暴露 resize 方法，供父组件在特殊时机手动调用
 * （例如抽屉展开后容器尺寸变了但 ResizeObserver 未触发）。
 */
defineExpose({
  resize: () => chart.value?.resize(),
})
</script>

<template>
  <div class="echart-wrapper">
    <!-- 空数据占位：不销毁实例，只覆盖一层提示，避免高度塌陷 -->
    <div v-if="empty" class="echart-empty" :style="containerStyle">
      <el-empty :description="emptyText" :image-size="80" />
    </div>

    <div
      v-show="!empty"
      ref="containerRef"
      class="echart-canvas"
      :style="containerStyle"
    />
  </div>
</template>

<style scoped>
.echart-wrapper {
  width: 100%;
}

.echart-canvas {
  width: 100%;
}

.echart-empty {
  display: flex;
  align-items: center;
  justify-content: center;
}
</style>
