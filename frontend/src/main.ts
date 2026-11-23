/**
 * 应用入口。
 *
 * 初始化顺序有讲究：
 *   1. 创建 Vue 应用
 *   2. 注册 Pinia（必须在 router 之前，因为路由守卫可能用到 store）
 *   3. 注册 Element Plus 图标（全局组件）
 *   4. 注册路由
 *   5. 挂载
 */

import { createApp } from 'vue'
import { createPinia } from 'pinia'
import ElementPlus from 'element-plus'
import zhCn from 'element-plus/es/locale/lang/zh-cn'
import * as ElementPlusIconsVue from '@element-plus/icons-vue'

import 'element-plus/dist/index.css'

import App from './App.vue'
import router from './router'

// 全局样式（放在 Element Plus 样式之后，便于覆盖其默认样式）
import './styles/main.css'

const app = createApp(App)

// ---- Pinia ----
app.use(createPinia())

// ---- Element Plus ----
// 使用中文语言包：分页控件、日期选择器等内置文案才会显示中文
app.use(ElementPlus, { locale: zhCn })

// ---- 图标 ----
// 全量注册为全局组件，模板里可直接写 <el-icon><DataLine /></el-icon>
// 图标本身很小（每个约 1KB），全量注册的代价可接受
for (const [name, component] of Object.entries(ElementPlusIconsVue)) {
  app.component(name, component)
}

// ---- 路由 ----
app.use(router)

// ---- 全局错误处理 ----
// 捕获组件渲染期间的未处理异常，避免整个页面白屏且控制台无提示
app.config.errorHandler = (err, _instance, info) => {
  console.error('[BiliInsight] 组件异常：', err, '\n位置：', info)
}

app.mount('#app')
