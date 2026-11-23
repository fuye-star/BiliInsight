<script setup lang="ts">
/**
 * 总览指标卡片。
 *
 * 【为什么单独封装】
 * 总览页有 6-8 个指标卡片，结构完全一致（图标 + 标签 + 大数字 + 辅助说明）。
 * 若在页面里复制粘贴 8 遍，改一次样式要改 8 处。
 */
import { computed } from 'vue'

import { formatNumber } from '@/utils/format'

const props = withDefaults(
  defineProps<{
    /** 指标名称 */
    label: string
    /** 指标数值 */
    value: number | string | null | undefined
    /** Element Plus 图标名 */
    icon?: string
    /** 主题色 */
    color?: string
    /** 是否把大数字格式化为「万/亿」 */
    format?: boolean
    /** 辅助说明（如"篇均 12,963"） */
    hint?: string
    /** 数值后缀单位 */
    suffix?: string
  }>(),
  {
    icon: 'DataLine',
    color: '#409eff',
    format: true,
    hint: '',
    suffix: '',
  },
)

/** 展示用的数值文本 */
const displayValue = computed(() => {
  if (props.value == null) return '-'
  if (typeof props.value === 'string') return props.value
  if (!props.format) return String(props.value)
  return formatNumber(props.value)
})
</script>

<template>
  <el-card shadow="hover" class="stat-card">
    <div class="stat-card__body">
      <!-- 图标：用内联样式传颜色，避免为每种颜色写一个 class -->
      <div
        class="stat-card__icon"
        :style="{ backgroundColor: `${color}1a`, color }"
      >
        <el-icon :size="22"><component :is="icon" /></el-icon>
      </div>

      <div class="stat-card__content">
        <div class="stat-card__label">{{ label }}</div>
        <div class="stat-card__value">
          {{ displayValue }}
          <span v-if="suffix" class="stat-card__suffix">{{ suffix }}</span>
        </div>
        <div v-if="hint" class="stat-card__hint">{{ hint }}</div>
      </div>
    </div>
  </el-card>
</template>

<style scoped>
.stat-card {
  /* 让卡片在栅格里等高 */
  height: 100%;
}

.stat-card :deep(.el-card__body) {
  padding: 16px;
}

.stat-card__body {
  display: flex;
  align-items: center;
  gap: 14px;
}

.stat-card__icon {
  width: 46px;
  height: 46px;
  border-radius: 10px;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}

.stat-card__content {
  min-width: 0;
  flex: 1;
}

.stat-card__label {
  font-size: 13px;
  color: #909399;
  line-height: 1.4;
}

.stat-card__value {
  font-size: 22px;
  font-weight: 600;
  color: #303133;
  line-height: 1.3;
  /* 数字等宽，多个卡片纵向排列时位数对齐 */
  font-variant-numeric: tabular-nums;
}

.stat-card__suffix {
  font-size: 13px;
  font-weight: 400;
  color: #909399;
  margin-left: 2px;
}

.stat-card__hint {
  font-size: 12px;
  color: #c0c4cc;
  line-height: 1.4;
  margin-top: 2px;
}
</style>
