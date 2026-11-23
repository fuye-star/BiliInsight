<script setup lang="ts">
/**
 * 弹幕情感分析页。
 *
 * 【页面结构】
 *   ① 全局情感指标卡片（总数 / 已分析 / 正向占比 / 主导情绪）
 *   ② 情感分布环形图 + 高频情绪标签
 *   ③ 情绪波动曲线（按播放进度）
 *   ④ 情感分值分布直方图
 *   ⑤ 词云（弹幕关键词）
 *   ⑥ 实时情感分析工具（输入任意文本立即分析）
 *
 * 【为什么做"实时分析工具"】
 * 页面上的图表是"已经分析好的历史数据"，
 * 而实时工具能直观演示"分析能力本身"，答辩演示时很有说服力：
 * 输入一句话立刻给出分值、倾向与情绪标签。
 */
import { computed, onMounted, ref } from 'vue'

import EChart from '@/components/EChart.vue'
import StatCard from '@/components/StatCard.vue'
import { aiApi, analyticsApi } from '@/api'
import { withErrorToast } from '@/api/request'
import {
  buildScoreHistogramOption,
  buildSentimentCurveOption,
  buildSentimentPieOption,
  buildWordCloudOption,
} from '@/utils/chartOptions'
import { formatNumber, formatPercent, sentimentColor } from '@/utils/format'

import type { SentimentAnalyzeResult, SentimentData, WordCloudData } from '@/types'

// ---------------------------------------------------------------------------
// 状态
// ---------------------------------------------------------------------------
const loading = ref(true)
const sentiment = ref<SentimentData | null>(null)
const wordcloud = ref<WordCloudData | null>(null)

/** 词云来源：弹幕内容 或 视频标题 */
const wordSource = ref<'danmaku' | 'title'>('danmaku')
const wordLoading = ref(false)

// ---- 实时分析 ----
const testText = ref('')
const analyzing = ref(false)
const testResult = ref<SentimentAnalyzeResult | null>(null)
const analyzeBackend = ref('')

/** 快捷测试样例：覆盖典型正向/中性/负向，便于快速演示 */
const samples = [
  { label: '正向', text: '太强了！这期质量真的高' },
  { label: '中性', text: '打卡，先收藏慢慢看' },
  { label: '负向', text: '有点失望，不如上一期' },
]

// ---------------------------------------------------------------------------
// 加载
// ---------------------------------------------------------------------------
async function loadAll() {
  loading.value = true
  const [s, w] = await Promise.all([
    withErrorToast(() => analyticsApi.sentiment({ segments: 20 }), null),
    withErrorToast(() => analyticsApi.wordcloud({ source: wordSource.value, limit: 60 }), null),
  ])
  sentiment.value = s
  wordcloud.value = w
  loading.value = false
}

async function reloadWordcloud() {
  wordLoading.value = true
  wordcloud.value = await withErrorToast(
    () => analyticsApi.wordcloud({ source: wordSource.value, limit: 60 }),
    wordcloud.value,
  )
  wordLoading.value = false
}

/** 执行实时情感分析 */
async function analyze() {
  const text = testText.value.trim()
  if (!text) {
    return
  }

  analyzing.value = true
  testResult.value = null

  const result = await withErrorToast(
    () => aiApi.analyzeSentiment({ text }),
    null,
  )

  if (result) {
    testResult.value = result
    analyzeBackend.value = result.backend
  }
  analyzing.value = false
}

/** 用样例填充并立即分析 */
function useSample(text: string) {
  testText.value = text
  analyze()
}

onMounted(loadAll)

// ---------------------------------------------------------------------------
// 图表配置
// ---------------------------------------------------------------------------
const pieOption = computed(() =>
  buildSentimentPieOption(sentiment.value?.distribution ?? []),
)

const curveOption = computed(() =>
  buildSentimentCurveOption(sentiment.value?.curve ?? []),
)

const histogramOption = computed(() =>
  buildScoreHistogramOption(sentiment.value?.score_histogram ?? []),
)

const wordcloudOption = computed(() =>
  buildWordCloudOption(wordcloud.value?.items ?? []),
)

/** 指标卡片 */
const statCards = computed(() => {
  const s = sentiment.value
  const positive = s?.distribution.find((d) => d.label === 'positive')
  const negative = s?.distribution.find((d) => d.label === 'negative')
  const topEmotion = s?.emotion_tags?.[0]

  return [
    {
      label: '弹幕总数',
      value: s?.total,
      icon: 'ChatDotRound',
      color: '#409eff',
      format: true,
      hint: `已分析 ${formatNumber(s?.analyzed ?? 0)} 条`,
    },
    {
      label: '正向占比',
      value: positive ? formatPercent(positive.pct, 1) : '-',
      icon: 'CircleCheck',
      color: '#67C23A',
      format: false,
      hint: `${formatNumber(positive?.count ?? 0)} 条`,
    },
    {
      label: '负向占比',
      value: negative ? formatPercent(negative.pct, 1) : '-',
      icon: 'Warning',
      color: '#F56C6C',
      format: false,
      hint: `${formatNumber(negative?.count ?? 0)} 条`,
    },
    {
      label: '主导情绪',
      value: topEmotion?.name ?? '-',
      icon: 'MagicStick',
      color: '#E6A23C',
      format: false,
      hint: topEmotion ? `出现 ${topEmotion.value} 次` : '暂无数据',
    },
  ]
})

const hasData = computed(() => (sentiment.value?.analyzed ?? 0) > 0)
</script>

<template>
  <div class="page-container">
    <!-- ==================== ① 指标卡片 ==================== -->
    <el-row :gutter="16" class="card-gap">
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

    <!-- ==================== 无数据提示 ==================== -->
    <el-card v-if="!loading && !hasData" shadow="never" class="card-gap">
      <el-empty description="还没有已分析的弹幕数据">
        <template #description>
          <div style="line-height: 2">
            <p>请先执行以下命令：</p>
            <p><code>python manage.py crawl --batch-danmaku 10</code></p>
            <p><code>python manage.py analyze_sentiment</code></p>
          </div>
        </template>
      </el-empty>
    </el-card>

    <template v-else>
      <!-- ==================== ② 分布 + 情绪标签 ==================== -->
      <el-row :gutter="16" class="card-gap">
        <el-col :xs="24" :md="10" style="margin-bottom: 16px">
          <el-card shadow="never" class="full-height">
            <template #header><span>情感分布</span></template>
            <EChart :option="pieOption" :loading="loading" height="320px" />
          </el-card>
        </el-col>

        <el-col :xs="24" :md="14" style="margin-bottom: 16px">
          <el-card shadow="never" class="full-height">
            <template #header><span>情绪标签分布</span></template>

            <div v-if="sentiment?.emotion_tags?.length" class="tag-cloud">
              <el-tag
                v-for="(tag, index) in sentiment.emotion_tags"
                :key="tag.name"
                :effect="index < 3 ? 'dark' : 'plain'"
                :type="index < 3 ? 'primary' : 'info'"
                class="tag-cloud__item"
                :style="{
                  fontSize: `${Math.max(12, Math.min(22, 12 + tag.value / 30))}px`,
                  padding: '6px 12px',
                }"
              >
                {{ tag.name }}
                <span style="opacity: 0.7; font-size: 12px">{{ tag.value }}</span>
              </el-tag>
            </div>

            <el-empty v-else description="暂无情绪标签" />
          </el-card>
        </el-col>
      </el-row>

      <!-- ==================== ③ 情绪波动 ==================== -->
      <el-card shadow="never" class="card-gap">
        <template #header>
          <div class="card-header">
            <span>情绪波动曲线（按视频播放进度）</span>
            <span class="text-muted" style="font-size: 12px">
              橙色虚线为中性基准 0.5
            </span>
          </div>
        </template>

        <EChart
          :option="curveOption"
          :loading="loading"
          :empty="!loading && !(sentiment?.curve?.length)"
          height="340px"
        />

        <div class="text-muted" style="font-size: 12px; margin-top: 8px">
          说明：曲线在 0.5 上方表示该进度区间的弹幕偏正面，下方偏负面。
          曲线中断处表示该区间没有弹幕数据。
        </div>
      </el-card>

      <!-- ==================== ④ 分值直方图 ==================== -->
      <el-card shadow="never" class="card-gap">
        <template #header><span>情感分值分布</span></template>
        <EChart :option="histogramOption" :loading="loading" height="260px" />
        <div class="text-muted" style="font-size: 12px; margin-top: 8px">
          分值越靠右越正面。两端集中说明观众态度鲜明，中间集中则说明态度温和。
        </div>
      </el-card>

      <!-- ==================== ⑤ 词云 ==================== -->
      <el-card shadow="never" class="card-gap">
        <template #header>
          <div class="card-header">
            <span>关键词词云</span>
            <el-radio-group v-model="wordSource" size="small" @change="reloadWordcloud">
              <el-radio-button value="danmaku">弹幕内容</el-radio-button>
              <el-radio-button value="title">视频标题</el-radio-button>
            </el-radio-group>
          </div>
        </template>

        <EChart
          :option="wordcloudOption"
          :loading="wordLoading"
          :empty="!wordLoading && !(wordcloud?.items?.length)"
          height="400px"
        />

        <div class="text-muted" style="font-size: 12px; margin-top: 8px">
          共统计 {{ formatNumber(wordcloud?.total_words ?? 0) }} 个词，
          去重后 {{ wordcloud?.unique_words ?? 0 }} 个。
          已过滤停用词（的/了/是 等）与标点数字。
        </div>
      </el-card>

      <!-- ==================== ⑥ 实时分析工具 ==================== -->
      <el-card shadow="never">
        <template #header>
          <div class="card-header">
            <span>实时情感分析</span>
            <el-tag v-if="analyzeBackend" size="small" effect="plain">
              后端：{{ analyzeBackend }}
            </el-tag>
          </div>
        </template>

        <el-input
          v-model="testText"
          type="textarea"
          :rows="3"
          maxlength="200"
          show-word-limit
          placeholder="输入任意弹幕或评论内容，例如：太强了！这期质量真的高"
        />

        <div style="margin-top: 12px">
          <el-button
            type="primary"
            :loading="analyzing"
            :disabled="!testText.trim()"
            :icon="'MagicStick'"
            @click="analyze"
          >
            分析情感
          </el-button>

          <span class="text-muted" style="margin-left: 12px; font-size: 12px">
            试试：
          </span>
          <el-button
            v-for="s in samples"
            :key="s.label"
            size="small"
            text
            type="primary"
            @click="useSample(s.text)"
          >
            {{ s.label }}
          </el-button>
        </div>

        <!-- 分析结果 -->
        <transition name="fade-slide">
          <div v-if="testResult" class="analyze-result">
            <el-divider />

            <el-descriptions :column="3" border>
              <el-descriptions-item label="情感分值">
                <span
                  class="text-strong"
                  :style="{ color: sentimentColor(testResult.label), fontSize: '18px' }"
                >
                  {{ testResult.score.toFixed(4) }}
                </span>
              </el-descriptions-item>

              <el-descriptions-item label="情感倾向">
                <el-tag :type="testResult.label === 'positive' ? 'success' : testResult.label === 'negative' ? 'danger' : 'info'">
                  {{ testResult.label_display }}
                </el-tag>
              </el-descriptions-item>

              <el-descriptions-item label="情绪标签">
                <template v-if="testResult.emotion_tags.length">
                  <el-tag
                    v-for="tag in testResult.emotion_tags"
                    :key="tag"
                    size="small"
                    effect="plain"
                    style="margin-right: 4px"
                  >
                    {{ tag }}
                  </el-tag>
                </template>
                <span v-else class="text-muted">无</span>
              </el-descriptions-item>
            </el-descriptions>

            <el-progress
              :percentage="Math.round(testResult.score * 100)"
              :color="sentimentColor(testResult.label)"
              :stroke-width="14"
              style="margin-top: 16px"
            />
            <div class="text-muted" style="font-size: 12px; text-align: center">
              0（最负面）━━━ 50（中性）━━━ 100（最正面）
            </div>
          </div>
        </transition>
      </el-card>
    </template>
  </div>
</template>

<style scoped>
.card-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.full-height {
  height: 100%;
}

.tag-cloud {
  display: flex;
  flex-wrap: wrap;
  /* 靠上对齐而不是垂直居中：标签少时不会孤零零悬在中间 */
  align-items: flex-start;
  align-content: flex-start;
  gap: 12px;
  padding: 16px 4px;
  /* 与左侧饼图高度接近，两侧视觉平衡；不设 min-height 避免大片空白 */
  min-height: 300px;
}

.tag-cloud__item {
  border-radius: 18px;
  /* 让字号变化更平滑，避免不同标签大小跳变突兀 */
  transition: transform 0.15s ease;
}

.tag-cloud__item:hover {
  transform: translateY(-2px);
}

.analyze-result {
  margin-top: 8px;
}
</style>
