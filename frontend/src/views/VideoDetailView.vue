<script setup lang="ts">
/**
 * 视频详情页。
 *
 * 【页面结构】
 *   ① 视频基本信息（封面、标题、UP主、发布时间、标签）
 *   ② 互动数据指标卡片
 *   ③ 该视频的弹幕情感分布 + 情绪波动曲线
 *   ④ 弹幕列表（可按情感筛选 + 分页）
 *
 * 【数据来源】
 *   视频信息  -> GET /api/videos/{bvid}/
 *   情感统计  -> GET /api/analytics/sentiment/?bvid=xxx
 *   弹幕列表  -> GET /api/videos/{bvid}/danmaku/
 * 三者并行请求，避免串行等待。
 */
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'

import EChart from '@/components/EChart.vue'
import StatCard from '@/components/StatCard.vue'
import { analyticsApi, videoApi } from '@/api'
import { withErrorToast } from '@/api/request'
import {
  buildScoreHistogramOption,
  buildSentimentCurveOption,
  buildSentimentPieOption,
} from '@/utils/chartOptions'
import {
  formatDate,
  formatDuration,
  formatNumber,
  formatPercent,
  sentimentColor,
  sentimentTagType,
} from '@/utils/format'

import type { Danmaku, SentimentData, VideoDetail } from '@/types'

const route = useRoute()
const router = useRouter()

const bvid = computed(() => String(route.params.bvid || ''))

// ---------------------------------------------------------------------------
// 状态
// ---------------------------------------------------------------------------
const loading = ref(true)
const video = ref<VideoDetail | null>(null)
const sentiment = ref<SentimentData | null>(null)

/**
 * 视频不存在的标记与错误信息。
 *
 * 【为什么用状态位而不是"延时自动跳回列表"】
 * 早期实现是：视频不存在 -> 1.5 秒后 router.replace 回列表。
 * 这个设计有两个问题：
 *   1. 用户正在读错误提示，页面突然跳走，体验很差
 *   2. 无法判断是"数据没了"还是"点击出错"，也来不及复制错误信息排查
 * 改为停留展示错误页 + 手动「返回列表 / 重试」按钮，把控制权交回用户。
 */
const notFound = ref(false)
const loadError = ref('')

// ---- 弹幕列表 ----
const danmakuLoading = ref(false)
const danmakuList = ref<Danmaku[]>([])
const danmakuTotal = ref(0)
const danmakuPage = ref(1)
const danmakuPageSize = ref(20)
const danmakuSentiment = ref('')

// ---------------------------------------------------------------------------
// 加载
// ---------------------------------------------------------------------------
async function loadAll() {
  loading.value = true

  // 视频信息与情感统计并行请求
  const [v, s] = await Promise.all([
    withErrorToast(() => videoApi.detail(bvid.value), null),
    withErrorToast(() => analyticsApi.sentiment({ bvid: bvid.value, segments: 10 }), null),
  ])

  video.value = v
  sentiment.value = s
  loading.value = false

  // 视频不存在时停留展示错误页，不自动跳转
  if (!v) {
    notFound.value = true
    loadError.value = `数据库中找不到视频 ${bvid.value}`
    return
  }

  loadDanmaku()
}

async function loadDanmaku() {
  danmakuLoading.value = true
  const result = await withErrorToast(
    () =>
      videoApi.danmaku(bvid.value, {
        page: danmakuPage.value,
        page_size: danmakuPageSize.value,
        sentiment: danmakuSentiment.value || undefined,
      }),
    null,
  )

  if (result) {
    danmakuList.value = result.results
    danmakuTotal.value = result.total
  } else {
    danmakuList.value = []
    danmakuTotal.value = 0
  }
  danmakuLoading.value = false
}

// 情感筛选变化时回到第一页
watch(danmakuSentiment, () => {
  danmakuPage.value = 1
  loadDanmaku()
})

onMounted(loadAll)

// ---------------------------------------------------------------------------
// 图表配置
// ---------------------------------------------------------------------------
const sentimentPieOption = computed(() =>
  buildSentimentPieOption(sentiment.value?.distribution ?? []),
)

const sentimentCurveOption = computed(() =>
  buildSentimentCurveOption(sentiment.value?.curve ?? []),
)

const histogramOption = computed(() =>
  buildScoreHistogramOption(sentiment.value?.score_histogram ?? []),
)

/** 互动数据卡片 */
const statCards = computed(() => {
  const v = video.value
  if (!v) return []
  return [
    {
      label: '播放量',
      value: v.view_count,
      icon: 'View',
      color: '#409eff',
      hint: `弹幕 ${formatNumber(v.danmaku_count)} · 评论 ${formatNumber(v.reply_count)}`,
    },
    {
      label: '点赞',
      value: v.like_count,
      icon: 'Star',
      color: '#67C23A',
      hint: `投币 ${formatNumber(v.coin_count)}`,
    },
    {
      label: '收藏',
      value: v.favorite_count,
      icon: 'Collection',
      color: '#E6A23C',
      hint: `分享 ${formatNumber(v.share_count)}`,
    },
    {
      label: '互动率',
      value: formatPercent(v.interaction_rate, 2, true),
      icon: 'TrendCharts',
      color: '#9A60B4',
      format: false,
      hint: '(点赞+投币+收藏)/播放',
    },
  ]
})

/** 是否已抓取弹幕（未抓取时情感图表为空） */
const hasDanmaku = computed(() => (sentiment.value?.analyzed ?? 0) > 0)

/**
 * 在B站打开原视频。
 *
 * 注意：模拟数据的 bvid 是虚构的，此链接会 404。
 * 模板中已用 v-if="!video.is_demo" 控制按钮只在真实数据上显示，
 * 因此这里不需要再判断——给用户一个点不通的按钮比不给更糟。
 */
function openOnBilibili() {
  const url = video.value?.source_url || `https://www.bilibili.com/video/${bvid.value}`
  window.open(url, '_blank')
}

/** 复制视频链接到剪贴板 */
async function copyLink() {
  const url = video.value?.source_url || `https://www.bilibili.com/video/${bvid.value}`

  try {
    // navigator.clipboard 在非 HTTPS 环境（如 http://localhost）也可用，
    // 但个别浏览器会拒绝，因此保留降级路径
    await navigator.clipboard.writeText(url)
    ElMessage.success('链接已复制到剪贴板')
  } catch {
    // 降级：用临时 textarea + document.execCommand
    const textarea = document.createElement('textarea')
    textarea.value = url
    textarea.style.position = 'fixed'
    textarea.style.opacity = '0'
    document.body.appendChild(textarea)
    textarea.select()
    try {
      document.execCommand('copy')
      ElMessage.success('链接已复制到剪贴板')
    } catch {
      ElMessage.error('复制失败，请手动复制：' + url)
    }
    document.body.removeChild(textarea)
  }
}

/** 复制 BV 号 */
async function copyBvid() {
  try {
    await navigator.clipboard.writeText(bvid.value)
    ElMessage.success(`已复制：${bvid.value}`)
  } catch {
    ElMessage.info(`BV 号：${bvid.value}`)
  }
}
</script>

<template>
  <div class="page-container" v-loading="loading">
    <!-- ==================== 返回 ==================== -->
    <div style="margin-bottom: 16px">
      <el-button :icon="'ArrowLeft'" text @click="router.back()">返回列表</el-button>
    </div>

    <!--
      ==================== 视频不存在的错误页 ====================
      早期实现是"1.5 秒后自动跳回列表"，用户体验很差：
      提示还没看清页面就跳走了，也无法判断原因。
      现在停留在此页，给出原因与手动操作入口。
    -->
    <el-card v-if="notFound && !loading" shadow="never">
      <el-result
        icon="warning"
        title="找不到该视频"
        :sub-title="loadError"
      >
        <template #extra>
          <div class="notfound-actions">
            <el-button type="primary" :icon="'ArrowLeft'" @click="router.push({ name: 'videos' })">
              返回视频列表
            </el-button>
            <el-button :icon="'Refresh'" @click="loadAll">重试</el-button>
          </div>

          <el-alert
            type="info"
            :closable="false"
            show-icon
            style="margin-top: 20px; text-align: left; max-width: 560px"
          >
            <template #title>可能的原因</template>
            <template #default>
              <div style="line-height: 2">
                1. 该视频已被删除或尚未抓取入库<br />
                2. <b>演示数据重建后 bvid 会变化</b>——若你重跑过
                <code>seed_demo</code>，旧链接会失效<br />
                3. 链接被手动修改过
              </div>
              <div style="margin-top: 10px">
                可以回到列表重新点击，或执行抓取命令获取新数据。
              </div>
            </template>
          </el-alert>
        </template>
      </el-result>
    </el-card>

    <!-- ==================== ① 视频基本信息 ==================== -->
    <el-card v-if="video" shadow="never" class="card-gap">
      <div class="video-header">
        <el-image
          :src="video.cover_url"
          referrerpolicy="no-referrer"
          fit="cover"
          class="video-header__cover"
        >
          <template #error>
            <div class="cover-fallback">
              <el-icon :size="28"><Picture /></el-icon>
            </div>
          </template>
        </el-image>

        <div class="video-header__info">
          <h2 class="video-header__title">
            {{ video.title }}
            <!-- 模拟数据标识：bvid 是虚构的，B站无法访问 -->
            <el-tag
              v-if="video.is_demo"
              type="warning"
              size="small"
              effect="light"
              style="vertical-align: middle; margin-left: 8px"
            >
              模拟数据
            </el-tag>
          </h2>

          <div class="video-header__meta">
            <el-tag v-if="video.partition" effect="plain">{{ video.partition }}</el-tag>
            <span>
              <el-icon><User /></el-icon>
              {{ video.up_name || '未知UP主' }}
            </span>
            <span>
              <el-icon><Clock /></el-icon>
              发布 {{ formatDate(video.pubdate) }}
            </span>
            <span>
              <el-icon><Timer /></el-icon>
              时长 {{ formatDuration(video.duration) }}
            </span>
            <el-tag
              type="info"
              effect="plain"
              size="small"
              style="cursor: pointer"
              title="点击复制 BV 号"
              @click="copyBvid"
            >
              BV {{ video.bvid }}
            </el-tag>
          </div>

          <div v-if="video.tag_list.length" class="video-header__tags">
            <el-tag
              v-for="tag in video.tag_list"
              :key="tag"
              size="small"
              type="info"
              effect="plain"
            >
              {{ tag }}
            </el-tag>
          </div>

          <div v-if="video.description" class="video-header__desc">
            {{ video.description }}
          </div>

          <div style="margin-top: 12px">
            <!--
              「在B站打开」只对真实数据展示。
              模拟数据的 bvid 是虚构的，点了会 404，
              给用户一个点不通的按钮比不给更糟糕。
            -->
            <el-button
              v-if="!video.is_demo"
              type="primary"
              :icon="'Link'"
              @click="openOnBilibili"
            >
              观看原视频
            </el-button>
            <el-button :icon="'DocumentCopy'" @click="copyLink">
              复制链接
            </el-button>

            <el-alert
              v-if="video.is_demo"
              type="warning"
              :closable="false"
              show-icon
              style="margin-top: 12px"
            >
              <template #title>
                这是<span style="font-weight: 600">模拟数据</span>，BV
                号为虚构值，在B站无法访问
              </template>
              <template #default>
                <div style="line-height: 1.8; margin-top: 4px">
                  数据由 <code>seed_demo</code> 命令生成，用于开发与演示。
                  要获得可点开验证的真实数据，请执行：<br />
                  <code>python manage.py crawl --partition 科技 --limit 20 --interval 5</code>
                </div>
              </template>
            </el-alert>
            <el-tag
              v-if="video.local_danmaku_count > 0"
              type="success"
              effect="plain"
              style="margin-left: 10px"
            >
              已抓取 {{ video.local_danmaku_count }} 条弹幕
            </el-tag>
            <el-tag v-else type="warning" effect="plain" style="margin-left: 10px">
              尚未抓取弹幕
            </el-tag>
          </div>
        </div>
      </div>
    </el-card>

    <!-- ==================== ② 互动指标 ==================== -->
    <el-row v-if="video" :gutter="16" class="card-gap">
      <el-col
        v-for="card in statCards"
        :key="card.label"
        :xs="12"
        :sm="12"
        :md="6"
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

    <!-- ==================== ③ 情感分析 ==================== -->
    <el-card shadow="never" class="card-gap">
      <template #header>
        <span>弹幕情感分析</span>
      </template>

      <el-alert
        v-if="!hasDanmaku"
        type="warning"
        :closable="false"
        show-icon
        title="该视频尚未抓取弹幕，或弹幕还没做情感分析"
      >
        <template #default>
          <div style="line-height: 1.9; margin-top: 6px">
            抓取弹幕：<code>python manage.py crawl --danmaku {{ bvid }}</code><br />
            分析情感：<code>python manage.py analyze_sentiment --video {{ bvid }}</code>
          </div>
        </template>
      </el-alert>

      <template v-else>
        <el-row :gutter="16">
          <el-col :xs="24" :md="10">
            <div class="sub-title">情感分布</div>
            <EChart :option="sentimentPieOption" height="300px" />
          </el-col>

          <el-col :xs="24" :md="14">
            <div class="sub-title">情绪波动（按播放进度）</div>
            <EChart :option="sentimentCurveOption" height="300px" />
          </el-col>
        </el-row>

        <el-row :gutter="16" style="margin-top: 20px">
          <el-col :xs="24" :md="14">
            <div class="sub-title">情感分值分布</div>
            <EChart :option="histogramOption" height="240px" />
          </el-col>

          <el-col :xs="24" :md="10">
            <div class="sub-title">高频情绪标签</div>
            <div class="emotion-tags">
              <el-tag
                v-for="tag in sentiment?.emotion_tags ?? []"
                :key="tag.name"
                :size="tag.value > 50 ? 'large' : 'default'"
                effect="light"
                style="margin: 4px"
              >
                {{ tag.name }} · {{ tag.value }}
              </el-tag>
              <el-empty
                v-if="!(sentiment?.emotion_tags?.length)"
                description="无情绪标签"
                :image-size="60"
              />
            </div>

            <div class="text-muted" style="font-size: 12px; margin-top: 12px">
              共分析 {{ sentiment?.analyzed ?? 0 }} 条弹幕（总计
              {{ sentiment?.total ?? 0 }} 条）
            </div>
          </el-col>
        </el-row>
      </template>
    </el-card>

    <!-- ==================== ④ 弹幕列表 ==================== -->
    <el-card shadow="never">
      <template #header>
        <div class="card-header">
          <span>弹幕列表（共 {{ danmakuTotal }} 条）</span>
          <el-radio-group v-model="danmakuSentiment" size="small">
            <el-radio-button value="">全部</el-radio-button>
            <el-radio-button value="positive">正向</el-radio-button>
            <el-radio-button value="neutral">中性</el-radio-button>
            <el-radio-button value="negative">负向</el-radio-button>
          </el-radio-group>
        </div>
      </template>

      <el-table :data="danmakuList" v-loading="danmakuLoading" stripe>
        <el-table-column label="出现时间" width="110" align="center">
          <template #default="{ row }">
            <el-tag size="small" effect="plain">
              {{ formatDuration(row.video_time) }}
            </el-tag>
          </template>
        </el-table-column>

        <el-table-column prop="content" label="弹幕内容" min-width="280" show-overflow-tooltip />

        <el-table-column label="情感" width="90" align="center">
          <template #default="{ row }">
            <el-tag
              v-if="row.sentiment_label"
              size="small"
              :type="sentimentTagType(row.sentiment_label)"
              effect="light"
            >
              {{ row.sentiment_label_display }}
            </el-tag>
            <span v-else class="text-muted">-</span>
          </template>
        </el-table-column>

        <el-table-column label="分值" width="80" align="right">
          <template #default="{ row }">
            <span
              v-if="row.sentiment_score != null"
              class="cell-num"
              :style="{ color: sentimentColor(row.sentiment_label) }"
            >
              {{ row.sentiment_score.toFixed(2) }}
            </span>
            <span v-else class="text-muted">-</span>
          </template>
        </el-table-column>

        <el-table-column label="情绪" width="120">
          <template #default="{ row }">
            <el-tag
              v-for="tag in row.emotion_tag_list"
              :key="tag"
              size="small"
              effect="plain"
              style="margin-right: 4px"
            >
              {{ tag }}
            </el-tag>
          </template>
        </el-table-column>

        <el-table-column label="发送时间" width="150" align="center">
          <template #default="{ row }">
            <span class="text-secondary" style="font-size: 12px">
              {{ formatDate(row.send_time, true) }}
            </span>
          </template>
        </el-table-column>

        <template #empty>
          <el-empty description="没有符合条件的弹幕" />
        </template>
      </el-table>

      <div class="pagination-wrapper">
        <el-pagination
          v-model:current-page="danmakuPage"
          v-model:page-size="danmakuPageSize"
          :total="danmakuTotal"
          :page-sizes="[20, 50, 100]"
          layout="total, sizes, prev, pager, next"
          background
          @current-change="loadDanmaku"
          @size-change="() => { danmakuPage = 1; loadDanmaku() }"
        />
      </div>
    </el-card>
  </div>
</template>

<style scoped>
.video-header {
  display: flex;
  gap: 20px;
}

.video-header__cover {
  width: 280px;
  height: 158px;
  border-radius: 8px;
  flex-shrink: 0;
  background: #f5f7fa;
}

.video-header__info {
  flex: 1;
  min-width: 0;
}

.video-header__title {
  margin: 0 0 12px 0;
  font-size: 19px;
  line-height: 1.45;
  color: #303133;
}

.video-header__meta {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 14px;
  color: #606266;
  font-size: 13px;
  margin-bottom: 10px;
}

.video-header__meta span {
  display: inline-flex;
  align-items: center;
  gap: 4px;
}

.video-header__tags {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-bottom: 10px;
}

.video-header__desc {
  color: #909399;
  font-size: 13px;
  line-height: 1.7;
  /* 简介可能很长，限制高度避免喧宾夺主 */
  max-height: 68px;
  overflow: hidden;
  white-space: pre-wrap;
}

.cover-fallback {
  width: 280px;
  height: 158px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: #f5f7fa;
  color: #c0c4cc;
  border-radius: 8px;
}

.card-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.sub-title {
  font-size: 13px;
  font-weight: 600;
  color: #606266;
  margin-bottom: 8px;
}

.emotion-tags {
  min-height: 180px;
  padding-top: 8px;
}

.pagination-wrapper {
  display: flex;
  justify-content: flex-end;
  margin-top: 16px;
}

.notfound-actions {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 12px;
}
</style>
