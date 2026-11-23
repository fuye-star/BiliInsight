<script setup lang="ts">
/**
 * 主布局：左侧导航 + 顶栏 + 内容区。
 *
 * 【为什么用布局组件而不是在每个页面重复写侧边栏】
 * 路由配置里把 MainLayout 作为父级，业务页面作为 children，
 * 这样切换页面时布局不会重新渲染，只有内容区更新，
 * 视觉上更稳定，也避免重复请求。
 */
import { computed, onMounted } from 'vue'
import { useRoute } from 'vue-router'

import { useAppStore } from '@/stores/app'

const route = useRoute()
const appStore = useAppStore()

/** 侧边栏菜单项（从路由表推导，避免两处维护） */
const menus = [
  { path: '/', title: '数据总览', icon: 'DataLine' },
  { path: '/videos', title: '视频数据', icon: 'VideoCamera' },
  { path: '/upusers', title: 'UP主排行', icon: 'User' },
  { path: '/sentiment', title: '情感分析', icon: 'ChatDotRound' },
  { path: '/ai', title: 'AI 助手', icon: 'MagicStick' },
]

/** 当前激活的菜单项 */
const activeMenu = computed(() => {
  // 视频详情页（/videos/BVxxx）应高亮"视频数据"菜单
  if (route.path.startsWith('/videos')) return '/videos'
  return route.path
})

/** 当前页面标题 */
const pageTitle = computed(() => (route.meta?.title as string) || 'BiliInsight')

/** 健康状态摘要（用于顶栏展示） */
const healthSummary = computed(() => {
  const h = appStore.health
  if (!h) {
    return { ok: false, text: '后端未连接', type: 'danger' as const }
  }
  if (h.status === 'healthy') {
    return { ok: true, text: '服务正常', type: 'success' as const }
  }
  return { ok: false, text: '部分依赖异常', type: 'warning' as const }
})

/** 各依赖的详细状态（悬浮提示里展示） */
const serviceDetails = computed(() => {
  const services = appStore.health?.services
  if (!services) return []
  return Object.entries(services).map(([key, value]) => ({
    key,
    ok: value.ok,
    detail: value.detail,
    latency: value.latency_ms,
  }))
})

onMounted(() => {
  // 预加载分区列表，供各页面的筛选下拉直接使用
  appStore.loadPartitions()
})
</script>

<template>
  <el-container class="layout">
    <!-- ============ 侧边栏 ============ -->
    <el-aside width="220px" class="layout__aside">
      <!-- 品牌区 -->
      <div class="brand">
        <div class="brand__logo">BI</div>
        <div class="brand__text">
          <div class="brand__name">BiliInsight</div>
          <div class="brand__desc">B站数据分析</div>
        </div>
      </div>

      <!-- 导航菜单 -->
      <el-menu
        :default-active="activeMenu"
        router
        class="layout__menu"
        background-color="#ffffff"
        text-color="#606266"
        active-text-color="#409eff"
      >
        <el-menu-item v-for="item in menus" :key="item.path" :index="item.path">
          <el-icon><component :is="item.icon" /></el-icon>
          <span>{{ item.title }}</span>
        </el-menu-item>
      </el-menu>

      <!-- 底部说明 -->
      <div class="layout__footer">
        <div class="text-muted" style="font-size: 12px; line-height: 1.6">
          数据仅用于学习研究<br />
          请遵守 B站 robots.txt
        </div>
      </div>
    </el-aside>

    <el-container>
      <!-- ============ 顶栏 ============ -->
      <el-header height="60px" class="layout__header">
        <div class="header__left">
          <h2 class="header__title">{{ pageTitle }}</h2>
        </div>

        <div class="header__right">
          <!-- 健康状态指示 -->
          <el-tooltip placement="bottom" :show-after="200">
            <template #content>
              <div style="line-height: 1.8">
                <div v-if="!serviceDetails.length">
                  后端服务未响应，请确认 8000 端口已启动
                </div>
                <div v-for="s in serviceDetails" :key="s.key">
                  {{ s.ok ? '✅' : '❌' }} {{ s.detail }}
                  <span v-if="s.ok" class="text-muted">（{{ s.latency }}ms）</span>
                </div>
              </div>
            </template>

            <el-tag :type="healthSummary.type" effect="light" round>
              <el-icon class="header__status-icon">
                <component :is="healthSummary.ok ? 'CircleCheck' : 'Warning'" />
              </el-icon>
              {{ healthSummary.text }}
            </el-tag>
          </el-tooltip>

          <!-- 手动刷新 -->
          <el-button
            :loading="appStore.healthLoading"
            circle
            :icon="'Refresh'"
            title="刷新服务状态"
            @click="appStore.refreshHealth()"
          />
        </div>
      </el-header>

      <!-- ============ 内容区 ============ -->
      <el-main class="layout__main">
        <router-view v-slot="{ Component }">
          <!-- 页面切换加淡入动画，避免生硬跳变 -->
          <transition name="fade-slide" mode="out-in">
            <component :is="Component" />
          </transition>
        </router-view>
      </el-main>
    </el-container>
  </el-container>
</template>

<style scoped>
.layout {
  height: 100vh;
}

/* ---------- 侧边栏 ---------- */
.layout__aside {
  display: flex;
  flex-direction: column;
  background: #ffffff;
  border-right: 1px solid #e4e7ed;
  /* 侧边栏固定，不随内容滚动 */
  overflow: hidden;
}

.brand {
  display: flex;
  align-items: center;
  gap: 10px;
  height: 60px;
  padding: 0 16px;
  border-bottom: 1px solid #e4e7ed;
  flex-shrink: 0;
}

.brand__logo {
  width: 36px;
  height: 36px;
  border-radius: 8px;
  background: linear-gradient(135deg, #409eff, #79bbff);
  color: #fff;
  font-weight: 700;
  font-size: 15px;
  display: flex;
  align-items: center;
  justify-content: center;
  letter-spacing: 0.5px;
}

.brand__name {
  font-size: 15px;
  font-weight: 600;
  color: #303133;
  line-height: 1.2;
}

.brand__desc {
  font-size: 11px;
  color: #909399;
  line-height: 1.4;
}

.layout__menu {
  flex: 1;
  padding-top: 8px;
  /* 菜单项过多时可滚动 */
  overflow-y: auto;
}

.layout__footer {
  padding: 12px 16px;
  border-top: 1px solid #e4e7ed;
  flex-shrink: 0;
}

/* ---------- 顶栏 ---------- */
.layout__header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  background: #ffffff;
  border-bottom: 1px solid #e4e7ed;
  padding: 0 20px;
  flex-shrink: 0;
}

.header__title {
  margin: 0;
  font-size: 17px;
  font-weight: 600;
  color: #303133;
}

.header__right {
  display: flex;
  align-items: center;
  gap: 12px;
}

.header__status-icon {
  margin-right: 4px;
  vertical-align: -2px;
}

/* ---------- 内容区 ---------- */
.layout__main {
  background: #f5f7fa;
  padding: 0;
  overflow-y: auto;
}
</style>
