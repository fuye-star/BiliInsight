/**
 * TypeScript 全局声明。
 *
 * 【本文件只放"全局声明"，不放可导入的类型】
 * 业务数据结构定义在 src/types/index.ts（普通 .ts 模块），
 * 因为 .d.ts 不能作为模块被 import。
 *
 * 本文件负责两件事：
 *   1) 让 TypeScript 认识 .vue 单文件组件
 *   2) 给 import.meta.env 上的自定义变量提供类型提示
 */

/// <reference types="vite/client" />

declare module '*.vue' {
  import type { DefineComponent } from 'vue'

  const component: DefineComponent<Record<string, unknown>, Record<string, unknown>, unknown>
  export default component
}

/** Vite 环境变量（对应 .env.development / .env.production） */
interface ImportMetaEnv {
  readonly VITE_API_BASE_URL: string
  readonly VITE_PROXY_TARGET?: string
  readonly VITE_APP_TITLE: string
}

interface ImportMeta {
  readonly env: ImportMetaEnv
}
