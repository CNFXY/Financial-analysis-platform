import { defineStore } from 'pinia'
import { ref, computed } from 'vue'

// 全局应用状态
export const useAppStore = defineStore('app', () => {
  // 侧边栏状态
  const sidebarCollapsed = ref(false)
  const sidebarMobileOpen = ref(false)

  // 主题（预留暗色/亮色切换）
  const theme = ref<'dark' | 'light'>('dark')

  // 全局加载
  const globalLoading = ref(false)
  const globalMessage = ref<{ type: 'success' | 'error' | 'info' | 'warning'; text: string } | null>(null)

  // WebSocket 连接状态
  const wsConnected = ref(false)
  const wsReconnecting = ref(false)

  // Getters
  const isMobile = computed(() => window.innerWidth < 768)

  function toggleSidebar() {
    if (isMobile.value) {
      sidebarMobileOpen.value = !sidebarMobileOpen.value
    } else {
      sidebarCollapsed.value = !sidebarCollapsed.value
    }
  }

  function closeSidebar() {
    sidebarMobileOpen.value = false
  }

  function setTheme(t: 'dark' | 'light') {
    theme.value = t
    document.documentElement.classList.toggle('dark', t === 'dark')
    localStorage.setItem('theme', t)
  }

  function showMessage(type: 'success' | 'error' | 'info' | 'warning', text: string, duration = 3000) {
    globalMessage.value = { type, text }
    setTimeout(() => { globalMessage.value = null }, duration)
  }

  return {
    sidebarCollapsed, sidebarMobileOpen, theme,
    globalLoading, globalMessage,
    wsConnected, wsReconnecting,
    isMobile,
    toggleSidebar, closeSidebar, setTheme, showMessage,
  }
})
