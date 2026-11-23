<script setup lang="ts">
/**
 * 视频数据列表页。
 *
 * 【功能】
 *   · 分页浏览全部视频
 *   · 按分区筛选
 *   · 关键词搜索（标题 / 简介 / 标签 / UP主名）
 *   · 播放量下限筛选
 *   · 多维度排序
 *   · 一行展开查看详情摘要
 *
 * 【搜索防抖的必要性】
 * 若每次输入都立刻请求，"数据分析"四个字会触发 4 次请求。
 * 这里用 400ms 防抖，只在用户停止输入后才发一次请求。
 */
import { computed, onMounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'

import { videoApi } from '@/api'
import { withErrorToast } from '@/api/request'
import { useAppStore } from '@/stores/app'
import { formatDate, formatNumber, formatPercent } from '@/utils/format'

import type { Video } from '@/types'

const router = useRouter()
const appStore = useAppStore()

// ---------------------------------------------------------------------------
// 查询条件
// ---------------------------------------------------------------------------
const keyword = ref('')
const partition = ref('')
const minView = ref<number | undefined>(undefined)
const ordering = ref('-view_count')

const page = ref(1)
const pageSize = ref(20)
const total = ref(0)

const loading = ref(false)
const videos = ref<Video[]>([])

/** 排序选项 */
const orderOptions = [
  { label: '播放量 高→低', value: '-view_count' },
  { label: '播放量 低→高', value: 'view_count' },
  { label: '互动率 高→低', value: '-interaction_rate' },
  { label: '点赞 高→低', value: '-like_count' },
  { label: '投币 高→低', value: '-coin_count' },
  { label: '收藏 高→低', value: '-favorite_count' },
  { label: '弹幕 多→少', value: '-danmaku_count' },
  { label: '发布时间 新→旧', value: '-pubdate' },
  { label: '发布时间 旧→新', value: 'pubdate' },
  { label: '时长 长→短', value: '-duration' },
]

/** 播放量下限选项 */
const minViewOptions = [
  { label: '不限', value: undefined },
  { label: '1 万以上', value: 10000 },
  { label: '5 万以上', value: 50000 },
  { label: '10 万以上', value: 100000 },
  { label: '50 万以上', value: 500000 },
]

// ---------------------------------------------------------------------------
// 数据加载
// ---------------------------------------------------------------------------
/** 加载当前页数据 */
async function load() {
  loading.value = true

  const result = await withErrorToast(
    () =>
      videoApi.list({
        page: page.value,
        page_size: pageSize.value,
        search: keyword.value || undefined,
        partition: partition.value || undefined,
        min_view: minView.value,
        ordering: ordering.value,
      }),
    null,
  )

  if (result) {
    videos.value = result.results
    total.value = result.total
  } else {
    videos.value = []
    total.value = 0
  }

  loading.value = false
}

/** 重置到第一页并重新加载（筛选条件变化时用） */
function reload() {
  page.value = 1
  load()
}

// ---------------------------------------------------------------------------
// 防抖搜索
// ---------------------------------------------------------------------------
let searchTimer: ReturnType<typeof setTimeout> | null = null

watch(keyword, () => {
  if (searchTimer) clearTimeout(searchTimer)
  searchTimer = setTimeout(() => {
    reload()
  }, 400)
})

// 筛选/排序变化时立即重新加载（这些是选择性操作，不需要防抖）
watch([partition, minView, ordering], () => {
  reload()
})

onMounted(() => {
  appStore.loadPartitions()
  load()
})

// ---------------------------------------------------------------------------
// 交互
// ---------------------------------------------------------------------------
/** 跳转详情 */
function goDetail(bvid: string) {
  router.push({ name: 'video-detail', params: { bvid } })
}

/**
 * 在B站打开原视频。
 *
 * 只对真实抓取的数据展示入口——模拟数据的 bvid 是虚构的，
 * 点开只会 404，给用户一个点不通的链接比不给更糟。
 */
function openOnBilibili(url: string) {
  window.open(url, '_blank')
}

/** 复制视频链接 */
async function copyVideoLink(url: string) {
  try {
    await navigator.clipboard.writeText(url)
    ElMessage.success('链接已复制到剪贴板')
  } catch {
    // 降级方案：clipboard API 在部分环境被拒绝
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
      ElMessage.error('复制失败：' + url)
    }
    document.body.removeChild(textarea)
  }
}

/** 清空全部筛选条件 */
function resetFilters() {
  keyword.value = ''
  partition.value = ''
  minView.value = undefined
  ordering.value = '-view_count'
  reload()
}

/** 是否有生效的筛选条件 */
const hasFilters = computed(
  () =>
    Boolean(keyword.value) ||
    Boolean(partition.value) ||
    minView.value !== undefined ||
    ordering.value !== '-view_count',
)
</script>

<template>
  <div class="page-container">
    <!-- ==================== 筛选栏 ==================== -->
    <el-card shadow="never" class="card-gap">
      <el-form :inline="true" @submit.prevent>
        <el-form-item label="关键词">
          <el-input
            v-model="keyword"
            placeholder="搜索标题 / 简介 / 标签 / UP主"
            clearable
            style="width: 260px"
            :prefix-icon="'Search'"
          />
        </el-form-item>

        <el-form-item label="分区">
          <el-select
            v-model="partition"
            placeholder="全部分区"
            clearable
            style="width: 160px"
          >
            <el-option label="全部分区" value="" />
            <el-option
              v-for="p in appStore.partitions"
              :key="p.id"
              :label="`${p.name}（${p.video_count}）`"
              :value="p.name"
            />
          </el-select>
        </el-form-item>

        <el-form-item label="播放量">
          <el-select v-model="minView" style="width: 140px">
            <el-option
              v-for="o in minViewOptions"
              :key="String(o.value)"
              :label="o.label"
              :value="o.value"
            />
          </el-select>
        </el-form-item>

        <el-form-item label="排序">
          <el-select v-model="ordering" style="width: 165px">
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
          <el-button v-if="hasFilters" text type="primary" @click="resetFilters">
            重置筛选
          </el-button>
        </el-form-item>
      </el-form>
    </el-card>

    <!-- ==================== 结果表格 ==================== -->
    <el-card shadow="never">
      <template #header>
        <div class="card-header">
          <span>
            共 <b>{{ total }}</b> 条视频
            <span v-if="partition" class="text-muted">（分区：{{ partition }}）</span>
            <span v-if="keyword" class="text-muted">（关键词：{{ keyword }}）</span>
          </span>
        </div>
      </template>

      <el-table
        :data="videos"
        v-loading="loading"
        stripe
        style="width: 100%"
        @row-click="(row: Video) => goDetail(row.bvid)"
      >
        <el-table-column type="index" label="#" width="50" align="center" />

        <el-table-column label="封面" width="120">
          <template #default="{ row }">
            <!-- 封面加载失败时显示占位，避免出现破图图标 -->
            <el-image
              :src="row.cover_url"
              referrerpolicy="no-referrer"
              fit="cover"
              style="width: 96px; height: 54px; border-radius: 4px"
              lazy
            >
              <template #error>
                <div class="cover-fallback">
                  <el-icon><Picture /></el-icon>
                </div>
              </template>
            </el-image>
          </template>
        </el-table-column>

        <el-table-column label="标题" min-width="300">
          <template #default="{ row }">
            <div class="title-row">
              <!--
                真实数据的标题可直接点击跳转B站（方便核对）；
                模拟数据不设链接，因为 bvid 是虚构的，点开只有 404。
              -->
              <a
                v-if="!row.is_demo"
                class="title-link text-ellipsis-2"
                :href="row.source_url"
                target="_blank"
                rel="noopener"
                :title="`在B站打开：${row.title}`"
                @click.stop
              >
                {{ row.title }}
              </a>
              <span v-else class="text-ellipsis-2" style="line-height: 1.4">
                {{ row.title }}
              </span>
            </div>

            <div class="text-muted" style="font-size: 12px; margin-top: 2px">
              <el-tag v-if="row.partition" size="small" effect="plain">
                {{ row.partition }}
              </el-tag>
              <!-- 模拟数据标识：让用户一眼分清哪些 bvid 是虚构的 -->
              <el-tag
                v-if="row.is_demo"
                size="small"
                type="warning"
                effect="light"
                style="margin-left: 4px"
              >
                模拟数据
              </el-tag>
              <span style="margin-left: 6px">{{ row.up_name || '未知UP主' }}</span>
            </div>
          </template>
        </el-table-column>

        <el-table-column label="时长" width="80" align="center">
          <template #default="{ row }">
            <span class="text-secondary" style="font-size: 12px">
              {{ row.duration_display }}
            </span>
          </template>
        </el-table-column>

        <el-table-column label="播放量" width="105" align="right" sortable>
          <template #default="{ row }">
            <span class="cell-num text-strong">{{ formatNumber(row.view_count) }}</span>
          </template>
        </el-table-column>

        <el-table-column label="点赞" width="90" align="right">
          <template #default="{ row }">
            <span class="cell-num">{{ formatNumber(row.like_count) }}</span>
          </template>
        </el-table-column>

        <el-table-column label="投币" width="90" align="right">
          <template #default="{ row }">
            <span class="cell-num">{{ formatNumber(row.coin_count) }}</span>
          </template>
        </el-table-column>

        <el-table-column label="互动率" width="100" align="right">
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

        <el-table-column label="发布时间" width="105" align="center">
          <template #default="{ row }">
            <span class="text-secondary" style="font-size: 12px">
              {{ formatDate(row.pubdate) }}
            </span>
          </template>
        </el-table-column>

        <el-table-column label="操作" width="140" align="center">
          <template #default="{ row }">
            <!--
              「原站」只对真实数据展示。
              模拟数据的 bvid 是虚构的，跳过去只有 404。
            -->
            <el-button
              v-if="!row.is_demo"
              size="small"
              text
              type="primary"
              :icon="'Link'"
              title="在B站打开原视频"
              @click.stop="openOnBilibili(row.source_url)"
            >
              原站
            </el-button>
            <el-tooltip
              v-else
              content="模拟数据的 BV 号为虚构值，B站无法访问"
              placement="top"
            >
              <el-button size="small" text disabled :icon="'Link'">
                原站
              </el-button>
            </el-tooltip>

            <el-button
              size="small"
              text
              :icon="'DocumentCopy'"
              title="复制链接"
              @click.stop="copyVideoLink(row.source_url)"
            >
              复制
            </el-button>
          </template>
        </el-table-column>

        <template #empty>
          <el-empty description="没有符合条件的视频">
            <el-button v-if="hasFilters" type="primary" @click="resetFilters">
              清空筛选条件
            </el-button>
          </el-empty>
        </template>
      </el-table>

      <!-- ==================== 分页 ==================== -->
      <div class="pagination-wrapper">
        <el-pagination
          v-model:current-page="page"
          v-model:page-size="pageSize"
          :total="total"
          :page-sizes="[10, 20, 50, 100]"
          layout="total, sizes, prev, pager, next, jumper"
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

.pagination-wrapper {
  display: flex;
  justify-content: flex-end;
  margin-top: 16px;
}

.cover-fallback {
  width: 96px;
  height: 54px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: #f5f7fa;
  border-radius: 4px;
  color: #c0c4cc;
}

/* 表格行可点击进入详情 */
:deep(.el-table__row) {
  cursor: pointer;
}

.title-row {
  display: flex;
  align-items: flex-start;
  gap: 4px;
}

/* 标题外链：默认沿用正文色，悬浮才变蓝加下划线，
   避免整张表格被蓝色链接淹没 */
.title-link {
  color: #303133;
  text-decoration: none;
  line-height: 1.4;
  transition: color 0.15s ease;
}

.title-link:hover {
  color: #409eff;
  text-decoration: underline;
}
</style>
