/**
 * Pinia 状态管理。
 *
 * 【本项目需要全局状态的只有两处】
 *  1. 后端健康状态 —— 顶栏持续显示"数据库是否正常"，多页面共用
 *  2. 分区列表     —— 多个页面的筛选下拉都要用，避免重复请求
 *
 * 其余数据（趋势、榜单等）都是页面级的一次性查询，
 * 直接在各视图里请求即可，放进 store 反而增加复杂度。
 */

import { defineStore } from 'pinia'
import { ref } from 'vue'

import { healthApi, videoApi } from '@/api'
import { withErrorToast } from '@/api/request'

import type { HealthData, Partition } from '@/types'

export const useAppStore = defineStore('app', () => {
  // -------------------------------------------------------------------------
  // 后端健康状态
  // -------------------------------------------------------------------------
  const health = ref<HealthData | null>(null)
  const healthLoading = ref(false)

  /** 后端整体是否可用 */
  const isHealthy = ref(false)

  /**
   * 刷新健康状态。
   *
   * @param silent 为 true 时不弹出错误提示（用于轮询场景）
   */
  async function refreshHealth(silent = false) {
    healthLoading.value = true
    try {
      health.value = await withErrorToast(
        () => healthApi.check(),
        null,
        { silent },
      )
      // 后端任一依赖异常时会返回 503，此时 withErrorToast 会走 fallback，
      // 因此这里以 health 是否有值为准
      isHealthy.value = health.value?.status === 'healthy'
    } finally {
      healthLoading.value = false
    }
  }

  // -------------------------------------------------------------------------
  // 分区列表（多页面共用，做一次性缓存）
  // -------------------------------------------------------------------------
  const partitions = ref<Partition[]>([])
  const partitionsLoaded = ref(false)

  /**
   * 加载分区列表。
   *
   * 加 loaded 标记做缓存：分区数据很少变动，
   * 多个页面切换时没必要重复请求。
   */
  async function loadPartitions(force = false) {
    if (partitionsLoaded.value && !force) return partitions.value

    partitions.value = await withErrorToast(
      () => videoApi.partitions(),
      [] as Partition[],
    )
    partitionsLoaded.value = true
    return partitions.value
  }

  /** 把分区列表转成下拉选项（供 el-select 使用） */
  function partitionOptions() {
    return partitions.value.map((p) => ({
      label: `${p.name}（${p.video_count}）`,
      value: p.name,
    }))
  }

  return {
    health,
    healthLoading,
    isHealthy,
    refreshHealth,

    partitions,
    partitionsLoaded,
    loadPartitions,
    partitionOptions,
  }
})
