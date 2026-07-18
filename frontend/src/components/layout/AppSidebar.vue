<script setup lang="ts">
import { computed } from 'vue'
import { useRoute, RouterLink } from 'vue-router'
import {
  HomeIcon, ChartBarIcon, BriefcaseIcon,
  ActivityIcon, DocumentIcon, CogIcon,
  ChevronLeftIcon, XIcon
} from '@/components/icons'
import { useUserStore } from '@/stores/user'

const props = defineProps<{
  collapsed: boolean
  mobileOpen: boolean
}>()

const emit = defineEmits<{
  close: []
}>()

const route = useRoute()
const userStore = useUserStore()

const navItems = computed(() => [
  { name: '首页', icon: HomeIcon, path: '/', requiresAuth: false },
  { name: '基金估算', icon: ChartBarIcon, path: '/fund-estimate', requiresAuth: true },
  { name: '组合分析', icon: BriefcaseIcon, path: '/portfolio', requiresAuth: true },
  { name: '实时行情', icon: ActivityIcon, path: '/realtime', requiresAuth: true },
  { name: '报告中心', icon: DocumentIcon, path: '/report', requiresAuth: true },
  ...(userStore.isAdmin ? [{ name: '系统管理', icon: CogIcon, path: '/admin', requiresAuth: true }] : []),
])

function isActive(path: string) {
  if (path === '/') return route.path === '/'
  return route.path.startsWith(path)
}
</script>

<template>
  <aside
    class="fixed left-0 top-0 bottom-0 z-40 flex flex-col transition-all duration-300 glass-strong border-r border-white/[0.06]"
    :class="[
      collapsed ? 'w-20' : 'w-64',
      mobileOpen ? '!w-64 translate-x-0' : '-translate-x-full md:translate-x-0'
    ]"
  >
    <!-- Logo 区域 -->
    <div class="h-16 flex items-center px-4 border-b border-white/[0.06]">
      <RouterLink to="/" class="flex items-center gap-3 group" @click="emit('close')">
        <!-- Logo 图标 -->
        <div class="w-9 h-9 rounded-xl bg-gradient-to-br from-gold-400 to-gold-600 flex items-center justify-center flex-shrink-0 shadow-lg shadow-gold/20 group-hover:shadow-gold/30 transition-shadow">
          <span class="text-surface-deep font-black text-sm">F</span>
        </div>
        <!-- 文字（展开时显示） -->
        <transition name="fade-text">
          <span v-if="!collapsed || mobileOpen" class="text-base font-bold text-gradient-gold whitespace-nowrap">
            FUND-OS
          </span>
        </transition>
      </RouterLink>

      <!-- 移动端关闭按钮 -->
      <button v-if="mobileOpen" class="ml-auto md:hidden p-1.5 text-gray-500 hover:text-white" @click="emit('close')">
        <XIcon class="w-5 h-5" />
      </button>
    </div>

    <!-- 导航菜单 -->
    <nav class="flex-1 py-4 px-3 space-y-1 overflow-y-auto">
      <RouterLink
        v-for="item in navItems"
        :key="item.path"
        :to="item.path"
        class="nav-item group flex items-center gap-3 px-3 py-2.5 rounded-xl transition-all duration-200"
        :class="isActive(item.path)
          ? 'bg-gold-400/10 text-gold-400 font-medium'
          : 'text-gray-500 hover:text-gray-300 hover:bg-white/[0.04]'"
        @click="emit('close')"
      >
        <component
          :is="item.icon"
          class="w-5 h-5 flex-shrink-0 transition-transform duration-200"
          :class="isActive(item.path) ? 'scale-110' : ''"
        />
        <transition name="fade-text">
          <span v-if="!collapsed || mobileOpen" class="text-sm whitespace-nowrap">{{ item.name }}</span>
        </transition>
        <!-- 激活指示器 -->
        <transition name="fade-text">
          <span v-if="isActive(item.path) && (!collapsed || mobileOpen)" class="ml-auto w-1.5 h-1.5 rounded-full bg-gold-400" />
        </transition>
      </RouterLink>
    </nav>

    <!-- 底部用户信息 -->
    <div v-if="userStore.isLoggedIn" class="p-3 border-t border-white/[0.06]">
      <div class="flex items-center gap-3 px-3 py-2 rounded-xl hover:bg-white/[0.03] cursor-pointer transition-colors">
        <div class="w-8 h-8 rounded-full bg-gradient-to-br from-cyan-400 to-cyan-600 flex items-center justify-center flex-shrink-0">
          <span class="text-xs font-bold text-surface-deep">{{ userStore.userName[0] }}</span>
        </div>
        <transition name="fade-text">
          <div v-if="!collapsed || mobileOpen" class="min-w-0">
            <p class="text-sm font-medium truncate">{{ userStore.userName }}</p>
            <p class="text-xs text-gray-500 truncate capitalize">{{ userStore.user?.role }}</p>
          </div>
        </transition>
      </div>
    </div>
  </aside>
</template>

<style scoped>
.fade-text-enter-active,
.fade-text-leave-active {
  transition: opacity 0.15s, transform 0.15s;
}
.fade-text-enter-from,
.fade-text-leave-to {
  opacity: 0;
  transform: translateX(-8px);
}
</style>