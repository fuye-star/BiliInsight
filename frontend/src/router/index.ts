/**
 * 路由配置。
 *
 * 【为什么全部用动态 import（懒加载）】
 * 若在文件顶部静态 import 所有页面组件，Vite 会把它们打进同一个 chunk，
 * 首屏要下载全部代码。改成 () => import(...) 后：
 *   · 每个页面独立成 chunk，访问时才加载
 *   · 首屏只需下载布局 + 当前页
 * 这是 README 中"路由懒加载"优化的具体实现。
 */

import { createRouter, createWebHistory, type RouteRecordRaw } from 'vue-router'

import MainLayout from '@/layouts/MainLayout.vue'

const routes: RouteRecordRaw[] = [
  {
    path: '/',
    component: MainLayout,
    // 所有业务页面都套在主布局（侧边栏 + 顶栏）内
    children: [
      {
        path: '',
        name: 'dashboard',
        component: () => import('@/views/DashboardView.vue'),
        meta: { title: '数据总览', icon: 'DataLine' },
      },
      {
        path: 'videos',
        name: 'videos',
        component: () => import('@/views/VideoListView.vue'),
        meta: { title: '视频数据', icon: 'VideoCamera' },
      },
      {
        path: 'videos/:bvid',
        name: 'video-detail',
        component: () => import('@/views/VideoDetailView.vue'),
        // hidden 表示不在侧边栏显示（详情页从列表进入）
        meta: { title: '视频详情', hidden: true },
      },
      {
        path: 'upusers',
        name: 'upusers',
        component: () => import('@/views/UpUserView.vue'),
        meta: { title: 'UP主排行', icon: 'User' },
      },
      {
        path: 'sentiment',
        name: 'sentiment',
        component: () => import('@/views/SentimentView.vue'),
        meta: { title: '情感分析', icon: 'ChatDotRound' },
      },
      {
        path: 'ai',
        name: 'ai',
        component: () => import('@/views/AiChatView.vue'),
        meta: { title: 'AI 助手', icon: 'MagicStick' },
      },
    ],
  },
  {
    // 兜底：未匹配的路径回到总览页
    path: '/:pathMatch(.*)*',
    redirect: '/',
  },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
  scrollBehavior() {
    // 切换页面时回到顶部，避免详情页滚动位置带到列表页
    return { top: 0 }
  },
})

/**
 * 全局前置守卫：设置页面标题。
 *
 * 好处：浏览器标签页与历史记录里能直接看出当前页面，
 * 调试多标签时很方便。
 */
router.beforeEach((to, _from, next) => {
  const appTitle = import.meta.env.VITE_APP_TITLE || 'BiliInsight'
  const pageTitle = to.meta?.title as string | undefined
  document.title = pageTitle ? `${pageTitle} · ${appTitle}` : appTitle
  next()
})

export default router
