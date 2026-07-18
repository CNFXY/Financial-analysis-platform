<script setup lang="ts">
import { ref, onMounted, onUnmounted } from 'vue'
import { useRoute, RouterLink, useRouter } from 'vue-router'
import { useUserStore } from '@/stores/user'
import { useAppStore } from '@/stores/app'
import MenuIcon from '@/components/icons/MenuIcon.vue'
import BellIcon from '@/components/icons/BellIcon.vue'
import LogoutIcon from '@/components/icons/LogoutIcon.vue'

const emit = defineEmits<{
  'toggle-sidebar': []
}>()

const route = useRoute()
const router = useRouter()
const userStore = useUserStore()
const appStore = useAppStore()

const showUserMenu = ref(false)
const currentTime = ref('')
let timer: ReturnType<typeof setInterval>

function updateTime() {
  const now = new Date()
  currentTime.value = now.toLocaleTimeString('zh-CN', {
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
  })
}

function handleLogout() {
  userStore.logout()
  router.push('/login')
}

onMounted(() => {
  updateTime()
  timer = setInterval(updateTime, 1000)
})

onUnmounted(() => clearInterval(timer))
</script>

<template>
  <header class="fixed top-0 right-0 z-20 h-16 flex items-center justify-between px-4 md:px-6 glass-strong border-b border-white/[0.06]"
    :class="{ 'md:left-64': !appStore.sidebarCollapsed, 'md:left-20': appStore.sidebarCollapsed }"
  >
    <!-- 左侧：菜单按钮 + 页面标题 -->
    <div class="flex items-center gap-3">
      <!-- 移动端菜单 -->
      <button class="lg:hidden p-2 text-gray-400 hover:text-white" @click="emit('toggle-sidebar')">
        <MenuIcon class="w-5 h-5" />
      </button>
      <!-- 桌面端折叠按钮 -->
      <button
        v-if="userStore.isLoggedIn"
        class="hidden lg:flex p-2 text-gray-500 hover:text-white hover:bg-white/5 rounded-lg transition-colors"
        @click="emit('toggle-sidebar')"
      >
        <MenuIcon class="w-5 h-5" />
      </button>

      <!-- 面包屑 / 页面标题 -->
      <div class="hidden sm:flex items-center gap-2 text-sm">
        <span class="text-gray-600">FUND-OS</span>
        <span class="text-gray-700">/</span>
        <span class="text-gray-300 font-medium">{{ (route.meta.title as string) || '' }}</span>
      </div>
    </div>

    <!-- 右侧：工具栏 -->
    <div class="flex items-center gap-2">
      <!-- 时间显示 -->
      <span class="hidden md:inline-flex text-xs font-mono text-gray-500 mr-2">{{ currentTime }}</span>

      <!-- WebSocket 状态 -->
      <div
        v-if="userStore.isLoggedIn"
        class="hidden sm:flex items-center gap-1.5 px-2 py-1 rounded-full text-xs"
        :class="appStore.wsConnected ? 'bg-emerald-400/10 text-emerald-400' : 'bg-red-400/10 text-red-400'"
      >
        <span class="w-1.5 h-1.5 rounded-full animate-pulse" :class="appStore.wsConnected ? 'bg-emerald-400' : 'bg-red-400'" />
        {{ appStore.wsConnected ? '实时' : '离线' }}
      </div>

      <!-- 通知 -->
      <button v-if="userStore.isLoggedIn" class="relative p-2 text-gray-500 hover:text-white hover:bg-white/5 rounded-lg transition-colors">
        <BellIcon class="w-5 h-5" />
        <span class="absolute top-1.5 right-1.5 w-2 h-2 bg-gold-400 rounded-full"></span>
      </button>

      <!-- 用户菜单 -->
      <div v-if="userStore.isLoggedIn" class="relative">
        <button
          class="flex items-center gap-2 px-2 py-1.5 rounded-lg hover:bg-white/5 transition-colors"
          @click="showUserMenu = !showUserMenu"
        >
          <div class="w-7 h-7 rounded-full bg-gradient-to-br from-gold-400 to-cyan-400 flex items-center justify-center">
            <span class="text-xs font-bold text-surface-deep">{{ userStore.userName[0] }}</span>
          </div>
          <span class="hidden md:block text-sm font-medium max-w-[100px] truncate">{{ userStore.userName }}</span>
        </button>

        <!-- 下拉菜单 -->
        <transition name="dropdown">
          <div v-if="showUserMenu" class="absolute right-0 mt-2 w-48 bg-surface-light border border-white/10 rounded-xl shadow-xl py-1 z-50">
            <div class="px-4 py-2 border-b border-white/5 mb-1">
              <p class="text-sm font-medium truncate">{{ userStore.user?.email || userStore.userName }}</p>
              <p class="text-xs text-gray-500 capitalize">{{ userStore.user?.subscription?.plan || 'free' }} plan</p>
            </div>
            <RouterLink
              v-if="userStore.isAdmin"
              to="/admin"
              class="flex items-center gap-2 px-4 py-2 text-sm text-gray-400 hover:text-white hover:bg-white/5 transition-colors"
              @click="showUserMenu = false"
            >
              <CogIcon class="w-4 h-4" />管理后台
            </RouterLink>
            <button
              class="flex items-center gap-2 w-full px-4 py-2 text-sm text-red-400 hover:bg-red-400/5 transition-colors"
              @click="handleLogout(); showUserMenu = false"
            >
              <LogoutIcon class="w-4 h-4" />退出登录
            </button>
          </div>
        </transition>
      </div>

      <!-- 未登录时显示登录按钮 -->
      <RouterLink
        v-if="!userStore.isLoggedIn && route.name !== 'Login'"
        to="/login"
        class="btn-primary text-sm px-4 py-1.5"
      >
        登录
      </RouterLink>
    </div>
  </header>
</template>

<script lang="ts">
export default {
  components: {
    CogIcon: () => import('@/components/icons/CogIcon.vue'),
  },
}
</script>

<style scoped>
.dropdown-enter-active,
.dropdown-leave-active {
  transition: all 0.15s ease;
}
.dropdown-enter-from,
.dropdown-leave-to {
  opacity: 0;
  transform: translateY(-8px) scale(0.95);
}

header {
  left: 0 !important;
  padding-left: calc(16px + 256px);
  transition: padding-left 0.3s ease;
}
@media (max-width: 768px) {
  header { padding-left: 16px !important; }
}
</style>