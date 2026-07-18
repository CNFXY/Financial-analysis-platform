<script setup lang="ts">
import { ref, onMounted, onUnmounted } from 'vue'
import { useRoute } from 'vue-router'
import { useAppStore } from '@/stores/app'
import AppSidebar from '@/components/layout/AppSidebar.vue'
import AppHeader from '@/components/layout/AppHeader.vue'
import AppFooter from '@/components/layout/AppFooter.vue'

const route = useRoute()
const appStore = useAppStore()

// 响应式处理
function handleResize() {
  if (window.innerWidth >= 768) {
    appStore.sidebarMobileOpen = false
  }
}

onMounted(() => {
  window.addEventListener('resize', handleResize)
  handleResize()
})

onUnmounted(() => {
  window.removeEventListener('resize', handleResize)
})

// 背景粒子效果
const showParticles = computed(() => route.name === 'Home')
</script>

<template>
  <div class="app-layout min-h-screen flex flex-col">
    <!-- 背景效果层 -->
    <BackgroundEffects />

    <!-- 侧边栏 -->
    <AppSidebar
      :collapsed="appStore.sidebarCollapsed"
      :mobile-open="appStore.sidebarMobileOpen"
      @close="appStore.closeSidebar"
    />

    <!-- 主内容区 -->
    <div
      class="flex-1 flex flex-col transition-all duration-300"
      :class="{
        'md:ml-64': !appStore.sidebarCollapsed,
        'md:ml-20': appStore.sidebarCollapsed,
      }"
    >
      <!-- 顶栏 -->
      <AppHeader @toggle-sidebar="appStore.toggleSidebar" />

      <!-- 页面内容 -->
      <main class="flex-1 p-4 md:p-6 lg:p-8 pt-20 md:pt-24 relative z-10">
        <slot />
      </main>

      <!-- 底部 -->
      <AppFooter />
    </div>

    <!-- 移动端遮罩 -->
    <transition name="fade">
      <div
        v-if="appStore.sidebarMobileOpen"
        class="fixed inset-0 bg-black/50 backdrop-blur-sm z-30 md:hidden"
        @click="appStore.closeSidebar"
      />
    </transition>
  </div>
</template>

<script lang="ts">
import { defineComponent, computed } from 'vue'
import BackgroundEffects from '@/components/effects/BackgroundEffects.vue'

export default defineComponent({
  name: 'AppLayout',
  components: {
    BackgroundEffects,
    AppSidebar: () => import('@/components/layout/AppSidebar.vue'),
    AppHeader: () => import('@/components/layout/AppHeader.vue'),
    AppFooter: () => import('@/components/layout/AppFooter.vue'),
  },
})
</script>

<style scoped>
.fade-enter-active,
.fade-leave-active {
  transition: opacity 0.3s;
}
.fade-enter-from,
.fade-leave-to {
  opacity: 0;
}
</style>
