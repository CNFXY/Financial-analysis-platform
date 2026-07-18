import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { authApi } from '@/api/auth'
import type { User, SubscriptionInfo } from '@/env'

export const useUserStore = defineStore('user', () => {
  // State
  const user = ref<User | null>(null)
  const token = ref<string | null>(localStorage.getItem('token'))
  const loading = ref(false)
  const error = ref<string | null>(null)

  // Getters
  const isLoggedIn = computed(() => !!token.value && !!user.value)
  const isAdmin = computed(() => user.value?.role === 'admin')
  const userName = computed(() => user.value?.username || '用户')
  const subscription = computed<SubscriptionInfo | undefined>(() => user.value?.subscription)

  // Actions
  async function login(username: string, password: string) {
    loading.value = true
    error.value = null
    try {
      const res = await authApi.login({ username, password })
      token.value = res.data.token
      user.value = res.data.user
      localStorage.setItem('token', res.data.token)
      localStorage.setItem('user', JSON.stringify(res.data.user))
      return true
    } catch (e: any) {
      error.value = e.message || '登录失败'
      return false
    } finally {
      loading.value = false
    }
  }

  async function register(data: { username: string; email: string; password: string }) {
    loading.value = true
    error.value = null
    try {
      const res = await authApi.register(data)
      token.value = res.data.token
      user.value = res.data.user
      localStorage.setItem('token', res.data.token)
      localStorage.setItem('user', JSON.stringify(res.data.user))
      return true
    } catch (e: any) {
      error.value = e.message || '注册失败'
      return false
    } finally {
      loading.value = false
    }
  }

  function logout() {
    token.value = null
    user.value = null
    localStorage.removeItem('token')
    localStorage.removeItem('user')
  }

  async function fetchProfile() {
    if (!token.value) return
    try {
      const res = await authApi.getProfile()
      user.value = res.data
      localStorage.setItem('user', JSON.stringify(res.data))
    } catch {
      logout()
    }
  }

  // 初始化：从本地存储恢复用户信息
  function init() {
    if (token.value) {
      const savedUser = localStorage.getItem('user')
      if (savedUser) {
        try {
          user.value = JSON.parse(savedUser)
        } catch {}
      }
    }
  }

  init()

  return {
    user, token, loading, error,
    isLoggedIn, isAdmin, userName, subscription,
    login, register, logout, fetchProfile,
  }
})
