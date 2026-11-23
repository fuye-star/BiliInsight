<script setup lang="ts">
/**
 * 数据总览页 —— 系统的核心看板。
 *
 * 【页面结构】
 *   ① 6 个指标卡片（总览数据）
 *   ② 播放量趋势折线图（可切换统计天数与分区）
 *   ③ 分区占比环形图（可切换按视频数/按播放量）
 *   ④ UP主排行横向柱状图（可切换排序维度）
 *   ⑤ 热榜视频表格（可切换排序维度，点击进入详情）
 *
 * 【数据加载策略】
 * 用 Promise.all 并行请求，而不是串行 await。
 * 后端接口响应时间约 20-80ms，串行 5 个接口需要 100-400ms，
 * 并行后总耗时取决于最慢的那个。这是最直接的性能优化。
 */
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'

import EChart from '@/components/EChart.vue'
import StatCard from '@/components/StatCard.vue'
import { analyticsApi, spiderApi } from '@/api'
import { withErrorToast } from '@/api/request'
import { useAppStore } from '@/stores/app'
import {
  buildPartitionPieOption,
  buildTrendOption,
  buildUpuserBarOption,
} from '@/utils/chartOptions'
import { formatDate, formatNumber, formatPercent } from '@/utils/format'

import type {
  CrawlResult,
  EnrichState,
  InteractionData,
  Overview,
  PartitionRatioData,
  TopUpusersData,
  TopVideosData,
  TrendData,
} from '@/types'

const router = useRouter()
const appStore = useAppStore()

// ---------------------------------------------------------------------------
// 状态
// ---------------------------------------------------------------------------
const loading = ref(true)

const overview = ref<Overview | null>(null)
const trend = ref<TrendData | null>(null)
const partitionRatio = ref<PartitionRatioData | null>(null)
const topUpusers = ref<TopUpusersData | null>(null)
const topVideos = ref<TopVideosData | null>(null)
const interaction = ref<InteractionData | null>(null)

// ---- 交互参数 ----
const trendDays = ref(14)
const trendPartition = ref('')
const pieMetric = ref<'video' | 'view'>('view')
const upuserOrder = ref('view_sum')
const videoOrder = ref('view_count')

/** UP主 排序维度的下拉选项 */
const upuserOrderOptions = [
  { label: '总播放量', value: 'view_sum' },
  { label: '作品数', value: 'video_count' },
  { label: '篇均播放', value: 'avg_view' },
  { label: '总点赞', value: 'like_sum' },
  { label: '粉丝数', value: 'follower_count' },
]

/** 视频排序维度的下拉选项 */
const videoOrderOptions = [
  { label: '播放量', value: 'view_count' },
  { label: '互动率', value: 'interaction_rate' },
  { label: '点赞数', value: 'like_count' },
  { label: '投币数', value: 'coin_count' },
  { label: '收藏数', value: 'favorite_count' },
]

// ---------------------------------------------------------------------------
// 数据加载
// ---------------------------------------------------------------------------
/** 加载总览相关的全部数据（并行） */
async function loadAll() {
  loading.value = true

  // Promise.all 并行请求：总耗时取决于最慢的接口，而非各接口之和
  const [ov, tr, pr, tu, tv, ia] = await Promise.all([
    withErrorToast(() => analyticsApi.overview(), null),
    withErrorToast(
      () => analyticsApi.trend({ days: trendDays.value, partition: trendPartition.value }),
      null,
    ),
    withErrorToast(() => analyticsApi.partitionRatio(), null),
    withErrorToast(
      () => analyticsApi.topUpusers({ limit: 10, order_by: upuserOrder.value }),
      null,
    ),
    withErrorToast(
      () => analyticsApi.topVideos({ limit: 10, order_by: videoOrder.value }),
      null,
    ),
    withErrorToast(() => analyticsApi.interaction({ limit: 5 }), null),
  ])

  overview.value = ov
  trend.value = tr
  partitionRatio.value = pr
  topUpusers.value = tu
  topVideos.value = tv
  interaction.value = ia

  loading.value = false
}

/** 只刷新趋势图（切换天数/分区时调用，避免整页 loading） */
async function reloadTrend() {
  trend.value = await withErrorToast(
    () => analyticsApi.trend({ days: trendDays.value, partition: trendPartition.value }),
    trend.value,
  )
}

/** 只刷新 UP主 排行榜 */
async function reloadUpusers() {
  topUpusers.value = await withErrorToast(
    () => analyticsApi.topUpusers({ limit: 10, order_by: upuserOrder.value }),
    topUpusers.value,
  )
}

/** 只刷新视频排行榜 */
async function reloadVideos() {
  topVideos.value = await withErrorToast(
    () => analyticsApi.topVideos({ limit: 10, order_by: videoOrder.value }),
    topVideos.value,
  )
}

// ---------------------------------------------------------------------------
// 数据更新（桌面版核心能力）
// ---------------------------------------------------------------------------
/**
 * 【为什么把"更新数据"做在界面上】
 *   这个项目原本只能靠命令行抓数据：
 *       python manage.py crawl --partition 科技 --limit 40
 *
 *   但打包成桌面应用后，使用者是老师/同学，不可能去敲命令。
 *   没有这个按钮，"打包后还能不能更新数据"就只是一个说法；
 *   有了它，联网点一下就能看到数据变成最新的 —— 这是可演示的能力。
 *
 * 【为什么默认走"全站热门"而不是"分区排行榜"】
 *   最初这里调用的是分区排行榜（ranking/v2）。实测下来有两个硬伤：
 *
 *     ① 排行榜每次返回的都是**同一批 Top 97**。这些视频抓过一次就都入库了，
 *        再点只会"更新 97 条、新增 0 条" —— 使用者会以为按钮坏了。
 *     ② 排行榜接口恰恰是**风控最严**的那个，点一次就可能被 -352 拦，
 *        之后每次点都失败（这就是"点一次后一直弹风控"的原因）。
 *
 *   换成"全站热门"（popular）后两个问题都解决了：
 *     · 它支持翻页，翻到后面的页几乎全是没见过的视频 → 每次点击都有新增
 *     · 实测连续抓 5 页 250 条零风控，额度比排行榜宽松得多
 *
 *   后端还维护了一个"翻页游标"，每次点击从上次的下一页继续，
 *   所以连续点几次能持续拿到新内容，而不是反复抓同一批。
 *
 * 【为什么抓取条数限制在几十条】
 *   同步接口要让用户等得起。热门榜 1 页约 50 条、耗时 1-3 秒；
 *   一次读 1-6 页（后端会自动跳过"已收录"的页），总耗时 5-20 秒。
 *   "补粉丝数 / 抓弹幕"是每项 1 次请求，几十项规定要几分钟，
 *   放在同一个请求里会让浏览器超时，因此拆到后台任务接口。
 */
const crawlPartition = ref('科技')
/** 「条数」= 本次希望新增多少条视频（热门模式按这个数停手） */
const crawlLimit = ref(5)
/** 抓取来源：popular（全站热门，推荐）/ partition（指定分区，风控敏感） */
const crawlSource = ref<'popular' | 'partition'>('popular')
const crawling = ref(false)
const crawlResult = ref<CrawlResult | null>(null)
const partitionChoices = ref<{ name: string; tid: number }[]>([])

/** 拉取可抓取的分区列表与默认参数 */
async function loadCrawlOptions() {
  const data = await withErrorToast(() => spiderApi.options(), null)
  if (data?.partitions?.length) {
    partitionChoices.value = data.partitions
    crawlPartition.value = data.default_partition || crawlPartition.value
    crawlLimit.value = data.default_limit || crawlLimit.value
  }
}

/** 执行一次抓取并刷新看板 */
async function doCrawl() {
  if (crawling.value) return
  crawling.value = true
  crawlResult.value = null
  try {
    const result = await spiderApi.crawl({
      source: crawlSource.value,
      partition: crawlPartition.value,
      limit: crawlLimit.value,
    })
    crawlResult.value = result

    // 新增了才报"成功"；没新增说明这几页都已收录，提示可以再点一次
    if (result.created > 0) {
      ElMessage.success(
        `抓取完成：新增 ${result.created} 条视频（耗时 ${result.elapsed}s）`,
      )
    } else {
      ElMessage.info('本次没有新视频，已为你往后翻了一页，再点一次试试')
    }

    // 后端已清缓存并重建索引，这里重新拉一遍就能看到新数据
    await loadAll()
  } catch (err) {
    // 被风控是最常见的情况，错误信息后端已给成人话，直接展示
    const message =
      (err as { message?: string })?.message ||
      '抓取失败，请检查网络连接后重试'
    ElMessage.warning(message)
  } finally {
    crawling.value = false
  }
}

// ---------------------------------------------------------------------------
// 深度更新（后台补全：UP主 粉丝数 + 弹幕）
// ---------------------------------------------------------------------------
/**
 * 【为什么需要"深度更新"】
 *   上面的「立即更新数据」只抓视频列表（封面、播放量、UP主名称）。
 *   但视频里有两类字段**排行榜接口不返回**，必须逐个补：
 *
 *     · UP主 粉丝数  —— 1 位 = 1 次请求，不补的话新 UP主 在排行榜里显示 0
 *     · 弹幕内容    —— 1 个视频 = 1 次请求，不补的话情感分析/词云没有新数据
 *
 *   这两项加起来可能几十上百次请求，**不能放在同步请求里**（浏览器会超时），
 *   所以后端用后台线程跑，前端轮询进度。
 *
 * 【为什么默认只补 10 个视频的弹幕】
 *   弹幕接口风控最紧（实测约 20 次后要冷却 5 分钟）。
 *   一次补 10 个视频约 1-2 分钟，属于"点完能等得到"的范围；
 *   要补更多可以用 scripts/grow_dataset.py 挂着跑。
 */
const enriching = ref(false)
const enrichState = ref<EnrichState | null>(null)
let enrichTimer: number | null = null

/** 停止轮询 */
function stopEnrichPolling() {
  if (enrichTimer !== null) {
    window.clearInterval(enrichTimer)
    enrichTimer = null
  }
}

/** 查询一次进度；结束后停止轮询并刷新看板 */
async function pollEnrich() {
  const state = await withErrorToast(() => spiderApi.enrichStatus(), null)
  if (!state) return
  enrichState.value = state

  if (!state.running) {
    stopEnrichPolling()
    enriching.value = false
    if (state.stage === 'error') {
      ElMessage.warning(state.error || '深度更新失败')
    } else {
      ElMessage.success(state.message || '深度更新完成')
    }
    // 粉丝数/弹幕变了，排行榜与情感分析都会变
    await loadAll()
  }
}

/** 启动深度更新 */
async function doDeepCrawl() {
  if (enriching.value) return
  enriching.value = true
  enrichState.value = null
  try {
    await spiderApi.enrichStart({ followers_limit: 300, danmaku_limit: 10 })
    ElMessage.info('深度更新已在后台启动，可以继续浏览其他页面')
    // 立即拉一次，避免等 2.5 秒才看到"正在补粉丝数"
    await pollEnrich()
    if (enriching.value) {
      enrichTimer = window.setInterval(pollEnrich, 2500)
    }
  } catch (err) {
    enriching.value = false
    ElMessage.warning(
      (err as { message?: string })?.message || '启动深度更新失败',
    )
  }
}

onMounted(() => {
  appStore.loadPartitions()
  loadCrawlOptions()
  loadAll()
  // 页面刷新后如果后台任务还在跑，继续显示进度
  pollEnrich().then(() => {
    if (enrichState.value?.running) {
      enriching.value = true
      enrichTimer = window.setInterval(pollEnrich, 2500)
    }
  })
})

onUnmounted(stopEnrichPolling)
// ---------------------------------------------------------------------------
// 图表配置（computed 会在数据变化时自动重算）
// ---------------------------------------------------------------------------
const trendOption = computed(() => buildTrendOption(trend.value?.points ?? []))

const pieOption = computed(() =>
  buildPartitionPieOption(partitionRatio.value?.items ?? [], pieMetric.value),
)

const upuserOption = computed(() => {
  const items = topUpusers.value?.items ?? []
  // 根据当前排序维度选择对应的数值
  const values = items.map((i) => {
    switch (upuserOrder.value) {
      case 'video_count':
        return i.video_count
      case 'avg_view':
        return i.avg_view
      case 'like_sum':
        return i.like_sum
      case 'follower_count':
        return i.follower_count
      default:
        return i.view_sum
    }
  })
  const metricLabel =
    upuserOrderOptions.find((o) => o.value === upuserOrder.value)?.label ?? '总播放量'
  return buildUpuserBarOption(
    items.map((i) => i.name),
    values,
    metricLabel,
  )
})

/** 当前指标卡片的数据（用 computed 便于统一维护） */
const statCards = computed(() => {
  const ov = overview.value
  return [
    {
      label: '收录视频',
      value: ov?.video_count,
      icon: 'VideoCamera',
      color: '#409eff',
      format: false,
      hint: `${ov?.partition_count ?? 0} 个分区`,
    },
    {
      label: '播放总量',
      value: ov?.total_view,
      icon: 'View',
      color: '#67C23A',
      hint: `篇均 ${formatNumber(ov?.avg_view ?? 0, 0)}`,
    },
    {
      label: '平均互动率',
      value: formatPercent(ov?.avg_interaction_rate, 2, true),
      icon: 'TrendCharts',
      color: '#E6A23C',
      format: false,
      hint: '(点赞+投币+收藏)/播放',
    },
    {
      label: 'UP主数量',
      value: ov?.upuser_count,
      icon: 'User',
      color: '#9A60B4',
      format: false,
      hint: '已收录作者',
    },
    {
      label: '入库弹幕',
      value: ov?.danmaku_count,
      icon: 'ChatDotRound',
      color: '#F56C6C',
      hint: `视频标记共 ${formatNumber(ov?.total_danmaku ?? 0)} 条`,
    },
    {
      label: '总点赞',
      value: ov?.total_like,
      icon: 'Star',
      color: '#73C0DE',
      hint: `收藏 ${formatNumber(ov?.total_favorite ?? 0)}`,
    },
  ]
})

/** 是否有任何数据（用于显示整体空状态） */
const isEmpty = computed(() => !loading.value && (overview.value?.video_count ?? 0) === 0)

/**
 * 数据来源提示。
 *
 * 【为什么必须在页面上说明】
 * seed_demo 生成的模拟数据，其 bvid 是虚构的，在B站搜索不到。
 * 若不说明，用户会误以为"爬虫抓的数据是假的"，
 * 从而对系统可信度产生错误判断——这比数据本身是模拟的更糟。
 *
 * 因此按真实/模拟的比例给出不同级别的提示：
 *   · 全部模拟 -> warning，并给出抓真实数据的命令
 *   · 混合     -> info，说明真实数据可点击验证
 *   · 全部真实 -> 不显示提示（无需打扰）
 *
 * 【为什么计数必须取自 overview 而不是榜单】
 *   早期实现用 `topVideos.items`（榜单前 10 条）估算比例，
 *   结果抓回真实数据后出现误导：
 *   播放量最高的前 10 条往往全是真实数据，于是 demoCount === 0，
 *   提示条**整个消失** —— 而库里其实还有 200 条模拟数据。
 *
 *   改成用 /api/analytics/overview/ 的全库计数后，
 *   "混合数据"的状态才是可信的。
 */
const dataSourceInfo = computed(() => {
  const ov = overview.value
  if (!ov || !ov.video_count) return null

  const totalCount = ov.video_count
  const { real_videos: realCount, demo_videos: demoCount } = ov

  // 全部是真实数据：不显示提示，避免无谓打扰
  if (demoCount === 0) return null

  if (realCount === 0) {
    return {
      type: 'warning' as const,
      title: `当前 ${totalCount} 条视频全部是模拟数据，BV 号为虚构值，在B站无法访问`,
      detail:
        '数据由 seed_demo 命令生成，用于开发与演示（数值分布贴近真实，但视频本身不存在）。' +
        '要获得可点击验证的真实数据，请执行：python manage.py crawl --partition 科技 --limit 100 --interval 5',
    }
  }

  return {
    type: 'info' as const,
    title: `混合数据：${realCount} 条真实抓取 + ${demoCount} 条模拟数据（共 ${totalCount} 条）`,
    detail:
      '带「模拟数据」标签的条目 BV 号为虚构值，不带标签的可点击标题跳转B站核对。' +
      '真实数据来自 B站排行榜接口，可在站内搜索 BV 号验证。',
  }
})

/** 跳转到视频详情 */
function goDetail(bvid: string) {
  router.push({ name: 'video-detail', params: { bvid } })
}

/**
 * 热榜表格行点击 → 进入详情。
 *
 * 【为什么封装成函数而不是写在模板里】
 * 早期模板里写的是内联箭头函数并带了 TS 类型注解：
 *     @row-click="(row: { bvid: string }) => goDetail(row.bvid)"
 * Vue 模板表达式由模板编译器解析，**不支持类型注解**，
 * 于是 `npm run build`（含 vue-tsc 类型检查）直接报 TS1005 语法错误：
 *     DashboardView.vue(483,33): error TS1005: ',' expected.
 *
 * Vite 开发服务器能容忍，所以开发阶段完全看不出来 ——
 * 直到要打生产包时才暴露。这类"只在构建期失败"的问题必须靠真跑一次 build 才能发现。
 */
function onRowClick(row: { bvid: string }) {
  goDetail(row.bvid)
}
</script>

<template>
  <div class="page-container">
    <!-- ==================== 整体空状态 ==================== -->
    <el-card v-if="isEmpty" shadow="never" class="card-gap">
      <el-empty description="数据库中还没有数据">
        <template #description>
          <p>数据库中还没有数据，请先导入数据：</p>
          <p style="margin-top: 8px">
            <code>python manage.py seed_demo</code>
            <span class="text-muted">（离线演示数据）</span>
          </p>
          <p>
            <code>python manage.py crawl --partition 科技</code>
            <span class="text-muted">（真实抓取）</span>
          </p>
        </template>
      </el-empty>
    </el-card>

    <!-- ==================== 数据来源提示 ==================== -->
    <!--
      区分真实抓取与模拟数据。若不提示，用户会以为
      页面上的 BV 号是真实的，去B站搜不到就会怀疑系统可信性。
    -->
    <el-alert
      v-if="!isEmpty && dataSourceInfo"
      :type="dataSourceInfo.type"
      :closable="false"
      show-icon
      class="card-gap"
    >
      <template #title>
        <span style="font-weight: 600">{{ dataSourceInfo.title }}</span>
      </template>
      <template #default>
        <div style="line-height: 1.9; margin-top: 4px">
          {{ dataSourceInfo.detail }}
        </div>
      </template>
    </el-alert>

    <!-- ==================== 数据更新 ==================== -->
    <!--
      桌面版核心能力：联网时点一下就能抓取最新数据。
      没有它，"打包后还能不能更新数据"就只是一个说法；
      有了它，使用者可以亲眼看到数据变成最新的。
    -->
    <el-card shadow="never" class="card-gap">
      <template #header>
        <div class="card-header">
          <span>数据更新</span>
          <span class="text-muted" style="font-size: 12px">
            联网后点一下即可抓取 B站 最新数据
          </span>
        </div>
      </template>

      <div class="crawl-bar">
        <el-radio-group v-model="crawlSource" :disabled="crawling" size="small">
          <el-radio-button value="popular">全站热门（推荐）</el-radio-button>
          <el-radio-button value="partition">指定分区</el-radio-button>
        </el-radio-group>

        <template v-if="crawlSource === 'partition'">
          <span class="crawl-label">分区</span>
          <el-select
            v-model="crawlPartition"
            style="width: 130px"
            :disabled="crawling"
          >
            <el-option
              v-for="p in partitionChoices"
              :key="p.tid"
              :label="p.name"
              :value="p.name"
            />
          </el-select>
        </template>

        <span class="crawl-label">条数</span>
        <el-input-number
          v-model="crawlLimit"
          :min="5"
          :max="200"
          :step="5"
          :disabled="crawling"
          style="width: 120px"
        />

        <el-button type="primary" :loading="crawling" @click="doCrawl">
          {{ crawling ? '正在抓取…' : '立即更新数据' }}
        </el-button>

        <el-button
          type="success"
          plain
          :loading="enriching"
          :disabled="crawling"
          @click="doDeepCrawl"
        >
          {{ enriching ? '深度更新中…' : '深度更新' }}
        </el-button>
      </div>

      <!-- 深度更新的进度反馈：它是后台任务，必须有可见进度 -->
      <div v-if="enrichState" class="enrich-box">
        <el-alert
          :type="
            enrichState.stage === 'error'
              ? 'error'
              : enrichState.running
                ? 'info'
                : 'success'
          "
          :closable="false"
          show-icon
        >
          <template #title>{{ enrichState.message }}</template>
          <div v-if="enrichState.total > 0" class="enrich-progress">
            <el-progress
              :percentage="
                Math.min(
                  100,
                  Math.round((enrichState.done / enrichState.total) * 100),
                )
              "
              :stroke-width="8"
            />
            <span class="text-muted">
              {{ enrichState.done }} / {{ enrichState.total }}
            </span>
          </div>
        </el-alert>
      </div>

      <div class="crawl-tip text-muted">
        <template v-if="crawlSource === 'popular'">
          全站热门支持翻页，每次点击都会自动往后翻，因此能持续抓到新视频（单次约 5-20 秒）。
        </template>
        <template v-else>
          分区排行榜每次返回同一批 Top 100，多为已收录内容；且该接口风控最严，容易被限流。
        </template>
      </div>

      <div v-if="crawlResult" class="crawl-result">
        <el-tag
          :type="crawlResult.created > 0 ? 'success' : 'info'"
          effect="plain"
        >
          新增 {{ crawlResult.created }} 条 / 更新 {{ crawlResult.updated }} 条
        </el-tag>
        <span class="text-muted">
          接口解析 {{ crawlResult.fetched }} 条 ·
          HTTP 请求 {{ crawlResult.requests }} 次 ·
          耗时 {{ crawlResult.elapsed }}s ·
          <template v-if="crawlResult.next_page">
            读了 {{ crawlResult.pages_read }} 页（下次从第 {{ crawlResult.next_page }} 页继续） ·
          </template>
          库内共 {{ crawlResult.video_total }} 条 ·
          索引 {{ crawlResult.index_count }} 条
        </span>
      </div>
    </el-card>

    <!-- ==================== ① 指标卡片 ==================== -->
    <el-row v-if="!isEmpty" :gutter="16" class="card-gap">
      <el-col
        v-for="card in statCards"
        :key="card.label"
        :xs="24"
        :sm="12"
        :md="8"
        :lg="4"
        style="margin-bottom: 16px"
      >
        <StatCard
          :label="card.label"
          :value="card.value"
          :icon="card.icon"
          :color="card.color"
          :format="card.format"
          :hint="card.hint"
        />
      </el-col>
    </el-row>

    <!-- ==================== ② 播放量趋势 ==================== -->
    <el-card shadow="never" class="card-gap">
      <template #header>
        <div class="card-header">
          <span>播放量趋势</span>
          <div class="card-header__actions">
            <el-select
              v-model="trendPartition"
              placeholder="全部分区"
              clearable
              size="small"
              style="width: 150px"
              @change="reloadTrend"
            >
              <el-option label="全部分区" value="" />
              <el-option
                v-for="p in appStore.partitions"
                :key="p.id"
                :label="p.name"
                :value="p.name"
              />
            </el-select>

            <el-radio-group v-model="trendDays" size="small" @change="reloadTrend">
              <el-radio-button :value="7">7天</el-radio-button>
              <el-radio-button :value="14">14天</el-radio-button>
              <el-radio-button :value="30">30天</el-radio-button>
            </el-radio-group>
          </div>
        </div>
      </template>

      <EChart
        :option="trendOption"
        :loading="loading"
        :empty="!loading && !(trend?.points?.length)"
        empty-text="所选时间范围内没有数据"
        height="330px"
      />

      <div class="text-muted" style="font-size: 12px; margin-top: 8px">
        提示：折线为播放量（左轴），柱状为当日发布视频数（右轴）。
        没有数据的日期不会出现在图中。
      </div>
    </el-card>

    <!-- ==================== ③ 分区占比 + ④ UP主排行 ==================== -->
    <el-row :gutter="16" class="card-gap">
      <el-col :xs="24" :lg="10" style="margin-bottom: 16px">
        <el-card shadow="never" class="full-height">
          <template #header>
            <div class="card-header">
              <span>分区分布</span>
              <el-radio-group v-model="pieMetric" size="small">
                <el-radio-button value="view">按播放量</el-radio-button>
                <el-radio-button value="video">按视频数</el-radio-button>
              </el-radio-group>
            </div>
          </template>

          <EChart
            :option="pieOption"
            :loading="loading"
            :empty="!loading && !(partitionRatio?.items?.length)"
            height="330px"
          />
        </el-card>
      </el-col>

      <el-col :xs="24" :lg="14" style="margin-bottom: 16px">
        <el-card shadow="never" class="full-height">
          <template #header>
            <div class="card-header">
              <span>UP主排行 Top 10</span>
              <el-select
                v-model="upuserOrder"
                size="small"
                style="width: 120px"
                @change="reloadUpusers"
              >
                <el-option
                  v-for="o in upuserOrderOptions"
                  :key="o.value"
                  :label="o.label"
                  :value="o.value"
                />
              </el-select>
            </div>
          </template>

          <EChart
            :option="upuserOption"
            :loading="loading"
            :empty="!loading && !(topUpusers?.items?.length)"
            height="330px"
          />
        </el-card>
      </el-col>
    </el-row>

    <!-- ==================== ⑤ 热榜视频 ==================== -->
    <el-card shadow="never" class="card-gap">
      <template #header>
        <div class="card-header">
          <span>视频热榜 Top 10</span>
          <el-select
            v-model="videoOrder"
            size="small"
            style="width: 130px"
            @change="reloadVideos"
          >
            <el-option
              v-for="o in videoOrderOptions"
              :key="o.value"
              :label="o.label"
              :value="o.value"
            />
          </el-select>
        </div>
      </template>

      <el-table
        :data="topVideos?.items ?? []"
        v-loading="loading"
        stripe
        style="width: 100%"
        @row-click="onRowClick"
      >
        <el-table-column type="index" label="#" width="50" align="center" />

        <el-table-column label="标题" min-width="320">
          <template #default="{ row }">
            <div class="video-title">
              <el-tag
                v-if="row.partition"
                size="small"
                effect="plain"
                :style="{ borderColor: 'transparent' }"
              >
                {{ row.partition }}
              </el-tag>
              <!-- 真实数据标题可点击跳B站；模拟数据不设链接（bvid 虚构） -->
              <a
                v-if="!row.is_demo"
                class="title-link text-ellipsis"
                :href="row.source_url"
                target="_blank"
                rel="noopener"
                :title="`在B站打开：${row.title}`"
                @click.stop
              >
                {{ row.title }}
              </a>
              <span v-else class="text-ellipsis">{{ row.title }}</span>
            </div>
            <div class="text-muted" style="font-size: 12px">
              <el-tag
                v-if="row.is_demo"
                size="small"
                type="warning"
                effect="light"
                style="margin-right: 4px"
              >
                模拟数据
              </el-tag>
              {{ row.up_name || '未知UP主' }} · {{ row.duration_display }}
            </div>
          </template>
        </el-table-column>

        <el-table-column label="播放量" width="110" align="right">
          <template #default="{ row }">
            <span class="cell-num text-strong">{{ formatNumber(row.view_count) }}</span>
          </template>
        </el-table-column>

        <el-table-column label="点赞" width="95" align="right">
          <template #default="{ row }">
            <span class="cell-num">{{ formatNumber(row.like_count) }}</span>
          </template>
        </el-table-column>

        <el-table-column label="投币" width="95" align="right">
          <template #default="{ row }">
            <span class="cell-num">{{ formatNumber(row.coin_count) }}</span>
          </template>
        </el-table-column>

        <el-table-column label="互动率" width="105" align="right">
          <template #default="{ row }">
            <el-tag
              size="small"
              :type="row.interaction_rate >= 0.1 ? 'success' : 'info'"
              effect="plain"
            >
              {{ formatPercent(row.interaction_rate, 2, true) }}
            </el-tag>
          </template>
        </el-table-column>

        <el-table-column label="发布时间" width="110" align="center">
          <template #default="{ row }">
            <span class="text-secondary" style="font-size: 12px">
              {{ formatDate(row.pubdate) }}
            </span>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- ==================== ⑥ 互动质量洞察 ==================== -->
    <el-card v-if="interaction" shadow="never">
      <template #header>
        <span>互动质量洞察</span>
      </template>

      <el-alert type="info" :closable="false" show-icon style="margin-bottom: 16px">
        <template #title>
          互动率 = (点赞 + 投币 + 收藏) / 播放量，比播放量更能反映内容质量。
          当前有
          <b>{{ interaction.high_quality_count }}</b>
          个视频的互动率达到
          <b>{{ formatPercent(interaction.high_quality_threshold, 0, true) }}</b>
          以上。
        </template>
      </el-alert>

      <el-table :data="interaction.top_interaction" stripe>
        <el-table-column type="index" label="#" width="50" align="center" />
        <el-table-column prop="title" label="标题" min-width="260" show-overflow-tooltip />
        <el-table-column prop="partition" label="分区" width="90" align="center" />
        <el-table-column prop="up_name" label="UP主" width="140" show-overflow-tooltip />
        <el-table-column label="播放量" width="110" align="right">
          <template #default="{ row }">
            <span class="cell-num">{{ formatNumber(row.view_count) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="互动率" width="110" align="right">
          <template #default="{ row }">
            <span class="cell-num text-strong" style="color: #67c23a">
              {{ formatPercent(row.interaction_rate, 2, true) }}
            </span>
          </template>
        </el-table-column>
      </el-table>
    </el-card>
  </div>
</template>

<style scoped>
.card-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.card-header__actions {
  display: flex;
  align-items: center;
  gap: 10px;
}

.full-height {
  height: 100%;
}

.video-title {
  display: flex;
  align-items: center;
  gap: 6px;
  min-width: 0;
}

/* 表格行可点击，给出手型光标提示 */
:deep(.el-table__row) {
  cursor: pointer;
}

/* 标题外链：默认沿用正文色，悬浮才变蓝加下划线，
   避免整张表格被蓝色链接淹没 */
.title-link {
  color: #303133;
  text-decoration: none;
  transition: color 0.15s ease;
}

.title-link:hover {
  color: #409eff;
  text-decoration: underline;
}

/* ---------------- 数据更新卡片 ---------------- */
.crawl-bar {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 10px;
}

.crawl-label {
  font-size: 13px;
  color: #606266;
}

.crawl-tip {
  font-size: 12px;
  line-height: 1.7;
  margin-top: 10px;
}

.enrich-box {
  margin-top: 12px;
}

.enrich-progress {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-top: 8px;
  font-size: 12px;
}

.enrich-progress :deep(.el-progress) {
  flex: 1;
}

.crawl-result {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 10px;
  margin-top: 14px;
  padding-top: 12px;
  border-top: 1px dashed #ebeef5;
  font-size: 12px;
}
</style>
