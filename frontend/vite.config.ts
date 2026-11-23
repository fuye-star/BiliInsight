/**
 * Vite 配置。
 *
 * 【关键配置说明】
 * 1) 端口固定 8080
 *    Django 的 CORS_ALLOWED_ORIGINS 里已登记 8080，
 *    若让 Vite 自动换端口会导致跨域被拦，因此这里显式固定。
 *
 * 2) 开发代理 /api -> http://127.0.0.1:8000
 *    这是解决前后端分离跨域最省事的方式：
 *    前端只请求同源的 /api/xxx，由 Vite 转发给 Django，
 *    浏览器不认为是跨域请求，也就不需要处理 CORS 预检。
 *    （后端的 CORS 配置仍保留，用于生产环境直连场景）
 *
 * 3) 手动分包（manualChunks）
 *    ECharts 与 Element Plus 体积较大，拆成独立 chunk 后：
 *      · 首次加载可以并行下载
 *      · 修改业务代码不会让第三方库的缓存失效
 */
import { fileURLToPath, URL } from 'node:url'

import vue from '@vitejs/plugin-vue'
import { defineConfig } from 'vite'

export default defineConfig({
  plugins: [vue()],

  resolve: {
    alias: {
      // 用 @ 指向 src，避免出现 ../../.. 这类难以维护的相对路径
      '@': fileURLToPath(new URL('./src', import.meta.url)),
    },
  },

  server: {
    port: 8080,
    // 端口被占用时直接报错，而不是静默换端口（否则会与后端 CORS 配置不一致）
    strictPort: true,
    open: false,
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
      },
      // 开发环境下 Django 托管的媒体文件也走代理，避免图片跨域
      '/media': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
      },
    },
  },

  build: {
    outDir: 'dist',
    // 生产环境不生成 sourcemap，减小产物体积
    sourcemap: false,
    chunkSizeWarningLimit: 1500,
    rollupOptions: {
      output: {
        manualChunks: {
          // 图表库单独分包
          echarts: ['echarts'],
          // UI 组件库单独分包
          element: ['element-plus', '@element-plus/icons-vue'],
          // 框架层单独分包
          vendor: ['vue', 'vue-router', 'pinia', 'axios'],
        },
      },
    },
  },
})
