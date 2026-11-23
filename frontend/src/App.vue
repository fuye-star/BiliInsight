<script setup lang="ts">
/**
 * 根组件。
 *
 * 职责很轻：只负责渲染路由出口，并提供 el-config-provider 统一配置。
 * 布局由 MainLayout 负责，避免根组件承担过多职责。
 */
import { onMounted } from 'vue'

import { useAppStore } from '@/stores/app'

const appStore = useAppStore()

onMounted(() => {
  // 应用启动时探测一次后端健康状态，供顶栏显示。
  // silent = true：首次探测失败不弹错误框，改为在顶栏显示红色标记，
  // 否则用户一进来就被弹窗打断。
  appStore.refreshHealth(true)
})
</script>

<template>
  <!-- size="default" 统一组件尺寸，避免各页面大小不一 -->
  <el-config-provider size="default">
    <router-view />
  </el-config-provider>
</template>
