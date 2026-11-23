<script setup lang="ts">
/**
 * UP主排行页。
 *
 * 【功能】
 *   · UP主 排行表格（可按粉丝数/作品数等排序）
 *   · 点开查看该 UP主 的详细数据（篇均播放、最高播放等）
 *
 * 【为什么篇均播放比总播放更有参考价值】
 * 总播放量受作品数量影响很大——发了 100 个视频的作者总播放自然高。
 * 篇均播放（总播放 / 作品数）才能反映"单条内容的质量水平"。
 * 因此这里把两个指标都展示出来。
 */
import { computed, onMounted, ref, watch } from 'vue'

import EChart from '@/components/EChart.vue'
import { analyticsApi, videoApi } from '@/api'
import { withErrorToast } from '@/api/request'
import { buildUpuserBarOption } from '@/utils/chartOptions'
import { formatNumber } from '@/utils/format'

import type { TopUpuserItem, UpUser } from '@/types'

const loading = ref(false)
const upusers = ref<UpUser[]>([])
const total = ref(0)
const page = ref(1)
const pageSize = ref(20)
const search = ref('')
const ordering = ref('-follower_count')

const orderOptions = [
  { label: '粉丝数 多→少', value: '-follower_count' },
  { label: '粉丝数 少→多', value: 'follower_count' },
  { label: '名称 A→Z', value: 'name' },
  { label: '入驻时间 新→旧', value: '-created_at' },
]

async function load() {
  loading.value = true
  const result = await withErrorToast(
    () =>
      videoApi.upusers({
        page: page.value,
        page_size: pageSize.value,
        search: search.value || undefined,
        ordering: ordering.value,
      }),
    null,
  )
  if (result) {
    upusers.value = result.results
    total.value = result.total
  } else {
    upusers.value = []
    total.value = 0
  }
  loading.value = false
}

function reload() {
  page.value = 1
  load()
}

// 搜索防抖
let searchTimer: ReturnType<typeof setTimeout> | null = null
watch(search, () => {
  if (searchTimer) clearTimeout(searchTimer)
  searchTimer = setTimeout(reload, 400)
})

watch(ordering, reload)

onMounted(() => {
  load()
  loadGlobalTop()
})

// ---------------------------------------------------------------------------
// 全局 Top 10 图表数据
// ---------------------------------------------------------------------------
/**
 * 全局榜单 Top 10。
 *
 * 【为什么不能用当前页数据画图】
 * 表格是分页的，若图表也用当前页的 10 条：
 *   · 第 1 页看到的是第 1-10 名（正确）
 *   · 第 2 页看到的是第 21-30 名，但图表标题仍写"粉丝数对比"
 * 这会造成严重误读——用户以为自己在看全局排行，实际是某一页的局部数据。
 *
 * 因此图表固定调用 analytics 接口取"全库 Top 10"，
 * 与表格的分页/排序完全解耦。
 *
 * 【为什么默认按「作品总播放量」而不是「粉丝数」】
 * B站的排行榜接口 **不返回 UP主 粉丝数**，
 * 因此真实抓取入库的 UP主，follower_count 全部是 0。
 * 早期这里把排序硬编码为 follower_count，结果是：
 *
 *     真实数据抓回来后，图表 Top 10 里一个真实 UP主 都没有 ——
 *     看起来像"UP主 排行没同步"，实际是排序字段上根本没有值。
 *
 * 而 view_sum（作品总播放量）由 videos 表实时聚合而来，
 * 真实数据一入库就有值，因此默认用它；
 * 粉丝数选项保留，方便切换对比。
 */
const globalTop = ref<TopUpuserItem[]>([])
const chartLoading = ref(false)

/** 图表排序指标：view_sum（作品总播放量，默认）/ follower_count（粉丝数） */
const chartMetric = ref<'view_sum' | 'follower_count'>('view_sum')

const chartMetricOptions = [
  { label: '作品总播放量', value: 'view_sum' },
  { label: '粉丝数', value: 'follower_count' },
]

/** 当前指标的显示名，用于图表标题与纵轴名 */
const chartMetricLabel = computed(
  () => chartMetricOptions.find((o) => o.value === chartMetric.value)?.label ?? '',
)

/**
 * 当前榜单中缺失粉丝数的 UP主 数量。
 *
 * 用于在界面上如实提示数据完整性：真实抓取的 UP主 没有粉丝数，
 * 直接显示 0 会让人误以为"数据坏了"，说明清楚反而更可信。
 */
const missingFollowerCount = computed(
  () => globalTop.value.filter((u) => !u.follower_count).length,
)

async function loadGlobalTop() {
  chartLoading.value = true
  const data = await withErrorToast(
    () => analyticsApi.topUpusers({ limit: 10, order_by: chartMetric.value }),
    null,
  )
  globalTop.value = data?.items ?? []
  chartLoading.value = false
}

// 切换指标后重新拉取：不同指标对应完全不同的榜单，不能复用上一次的结果
watch(chartMetric, loadGlobalTop)

const fanChartOption = computed(() =>
  buildUpuserBarOption(
    globalTop.value.map((u) => u.name),
    globalTop.value.map((u) =>
      chartMetric.value === 'view_sum' ? u.view_sum : u.follower_count,
    ),
    chartMetricLabel.value,
  ),
)
</script>

<template>
  <div class="page-container">
    <!-- ==================== 筛选 ==================== -->
    <el-card shadow="never" class="card-gap">
      <el-form :inline="true" @submit.prevent>
        <el-form-item label="搜索">
          <el-input
            v-model="search"
            placeholder="输入 UP主 名称"
            clearable
            style="width: 220px"
            :prefix-icon="'Search'"
          />
        </el-form-item>

        <el-form-item label="排序">
          <el-select v-model="ordering" style="width: 170px">
            <el-option
              v-for="o in orderOptions"
              :key="o.value"
              :label="o.label"
              :value="o.value"
            />
          </el-select>
        </el-form-item>

        <el-form-item>
          <el-button :icon="'Refresh'" @click="load">刷新</el-button>
        </el-form-item>
      </el-form>
    </el-card>

    <!-- ==================== 全局榜单 Top 10 ==================== -->
    <el-card shadow="never" class="card-gap">
      <template #header>
        <div class="card-header">
          <span>{{ chartMetricLabel }} Top 10</span>
          <div style="display: flex; align-items: center; gap: 12px">
            <span class="text-muted" style="font-size: 12px">
              全库排行，与下方表格的分页无关
            </span>
            <!-- 指标切换：默认总播放量，因为真实数据拿不到粉丝数 -->
            <el-radio-group v-model="chartMetric" size="small">
              <el-radio-button
                v-for="o in chartMetricOptions"
                :key="o.value"
                :value="o.value"
              >
                {{ o.label }}
              </el-radio-button>
            </el-radio-group>
          </div>
        </div>
      </template>

      <!--
        数据完整性提示：粉丝数来自模拟数据，真实抓取的 UP主 没有该字段。
        与其让用户看到一片 0 以为系统坏了，不如直接说清楚原因。
      -->
      <el-alert
        v-if="chartMetric === 'follower_count' && missingFollowerCount"
        type="info"
        :closable="false"
        show-icon
        style="margin-bottom: 12px"
      >
        <template #title>
          榜单中有 {{ missingFollowerCount }} 位 UP主 缺失粉丝数
        </template>
        B站排行榜接口不返回 UP主 粉丝数，因此真实抓取入库的 UP主 该字段为空。
        想看到真实数据，请切换到「作品总播放量」。
      </el-alert>

      <EChart
        :option="fanChartOption"
        :loading="chartLoading"
        :empty="!chartLoading && !globalTop.length"
        height="360px"
      />
    </el-card>

    <!-- ==================== 表格 ==================== -->
    <el-card shadow="never">
      <template #header>
        <span>共 <b>{{ total }}</b> 位 UP主</span>
      </template>

      <el-table :data="upusers" v-loading="loading" stripe>
        <el-table-column type="index" label="#" width="50" align="center" />

        <el-table-column label="UP主" min-width="200">
          <template #default="{ row }">
            <div class="upuser-cell">
              <el-avatar :size="34" :src="row.avatar">
                {{ (row.name || '?').slice(0, 1) }}
              </el-avatar>
              <div style="min-width: 0">
                <div class="text-ellipsis text-strong">{{ row.name }}</div>
                <div class="text-muted" style="font-size: 12px">
                  mid: {{ row.mid }}
                </div>
              </div>
            </div>
          </template>
        </el-table-column>

        <el-table-column label="粉丝数" width="120" align="right" sortable>
          <template #default="{ row }">
            <span class="cell-num text-strong">
              {{ formatNumber(row.follower_count) }}
            </span>
          </template>
        </el-table-column>

        <el-table-column label="收录作品" width="110" align="right">
          <template #default="{ row }">
            <span class="cell-num">{{ row.video_count }}</span>
          </template>
        </el-table-column>

        <el-table-column label="状态" width="110" align="center">
          <template #default="{ row }">
            <!-- 用收录作品数粗略区分"活跃作者"与"仅少量收录" -->
            <el-tag
              size="small"
              :type="row.video_count >= 5 ? 'success' : 'info'"
              effect="plain"
            >
              {{ row.video_count >= 5 ? '作品较多' : '少量收录' }}
            </el-tag>
          </template>
        </el-table-column>

        <el-table-column label="简介" min-width="200">
          <template #default="{ row }">
            <span class="text-muted" style="font-size: 12px">
              {{ row.sign || '-' }}
            </span>
          </template>
        </el-table-column>

        <template #empty>
          <el-empty description="没有符合条件的 UP主" />
        </template>
      </el-table>

      <div class="pagination-wrapper">
        <el-pagination
          v-model:current-page="page"
          v-model:page-size="pageSize"
          :total="total"
          :page-sizes="[10, 20, 50]"
          layout="total, sizes, prev, pager, next"
          background
          @current-change="load"
          @size-change="reload"
        />
      </div>
    </el-card>
  </div>
</template>

<style scoped>
.card-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.upuser-cell {
  display: flex;
  align-items: center;
  gap: 10px;
}

.pagination-wrapper {
  display: flex;
  justify-content: flex-end;
  margin-top: 16px;
}
</style>
