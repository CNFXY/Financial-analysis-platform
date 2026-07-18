<script setup lang="ts">
import { ref } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { useUserStore } from '@/stores/user'

const router = useRouter()
const route = useRoute()
const userStore = useUserStore()

const form = ref({ username: '', password: '' })
const loading = ref(false)
const error = ref('')

async function handleLogin() {
  if (!form.value.username || !form.value.password) return
  loading.value = true
  error.value = ''

  const success = await userStore.login(form.value.username, form.value.password)
  loading.value = false

  if (success) {
    const redirect = (route.query.redirect as string) || '/'
    router.push(redirect)
  } else {
    error.value = '用户名或密码错误'
  }
}
</script>

<template>
  <div class="min-h-screen flex items-center justify-center -mt-16 px-4">
    <div class="w-full max-w-md">
      <!-- Logo -->
      <div class="text-center mb-8">
        <div class="inline-flex items-center justify-center w-14 h-14 rounded-2xl bg-gradient-to-br from-gold-400 to-gold-600 shadow-lg shadow-gold-400/20 mb-4">
          <span class="text-surface-deep font-black text-xl">F</span>
        </div>
        <h1 class="text-2xl font-bold text-white">FUND-OS</h1>
        <p class="text-sm text-gray-500 mt-1">登录以继续使用</p>
      </div>

      <!-- 登录表单 -->
      <div class="card p-6 space-y-5">
        <div v-if="error" class="px-4 py-2.5 rounded-lg bg-red-400/10 border border-red-400/15 text-red-400 text-sm">
          {{ error }}
        </div>

        <div>
          <label class="block text-xs text-gray-500 mb-1.5 uppercase tracking-wider">用户名</label>
          <input v-model="form.username" type="text" placeholder="请输入用户名" class="input-base" />
        </div>

        <div>
          <label class="block text-xs text-gray-500 mb-1.5 uppercase tracking-wider">密码</label>
          <input v-model="form.password" type="password" placeholder="请输入密码" class="input-base" @keyup.enter="handleLogin" />
        </div>

        <button :disabled="loading || !form.username || !form.password"
                class="btn-primary w-full py-3"
                @click="handleLogin">
          {{ loading ? '登录中...' : '登录' }}
        </button>

        <p class="text-center text-sm text-gray-600">
          还没有账号？
          <router-link to="/register" class="text-gold-400 hover:text-gold-300 transition-colors">注册账号</router-link>
        </p>
      </div>
    </div>
  </div>
</template>