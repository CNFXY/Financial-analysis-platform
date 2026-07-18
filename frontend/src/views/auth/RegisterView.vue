<script setup lang="ts">
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { useUserStore } from '@/stores/user'

const router = useRouter()
const userStore = useUserStore()

const form = ref({ username: '', email: '', password: '', confirmPassword: '' })
const loading = ref(false)
const error = ref('')

async function handleRegister() {
  if (form.value.password !== form.value.confirmPassword) {
    error.value = '两次密码输入不一致'
    return
  }
  if (form.value.password.length < 6) {
    error.value = '密码至少6位'
    return
  }
  loading.value = true
  error.value = ''

  const success = await userStore.register({
    username: form.value.username,
    email: form.value.email,
    password: form.value.password,
  })

  loading.value = false

  if (success) {
    router.push('/')
  } else {
    error.value = '注册失败，请稍后重试'
  }
}
</script>

<template>
  <div class="min-h-screen flex items-center justify-center -mt-16 px-4">
    <div class="w-full max-w-md">
      <div class="text-center mb-8">
        <div class="inline-flex items-center justify-center w-14 h-14 rounded-2xl bg-gradient-to-br from-cyan-400 to-gold-400 shadow-lg shadow-cyan-400/10 mb-4">
          <span class="text-surface-deep font-black text-xl">F</span>
        </div>
        <h1 class="text-2xl font-bold text-white">
          创建账号
        </h1>
        <p class="text-sm text-gray-500 mt-1">
          注册以使用 FUND-OS 全部功能
        </p>
      </div>

      <div class="card p-6 space-y-5">
        <div
          v-if="error"
          class="px-4 py-2.5 rounded-lg bg-red-400/10 border border-red-400/15 text-red-400 text-sm"
        >
          {{ error }}
        </div>

        <div>
          <label class="block text-xs text-gray-500 mb-1.5 uppercase tracking-wider">用户名</label>
          <input
            v-model="form.username"
            type="text"
            placeholder="设置用户名"
            class="input-base"
          >
        </div>

        <div>
          <label class="block text-xs text-gray-500 mb-1.5 uppercase tracking-wider">邮箱</label>
          <input
            v-model="form.email"
            type="email"
            placeholder="your@email.com"
            class="input-base"
          >
        </div>

        <div>
          <label class="block text-xs text-gray-500 mb-1.5 uppercase tracking-wider">密码</label>
          <input
            v-model="form.password"
            type="password"
            placeholder="至少6位"
            class="input-base"
          >
        </div>

        <div>
          <label class="block text-xs text-gray-500 mb-1.5 uppercase tracking-wider">确认密码</label>
          <input
            v-model="form.confirmPassword"
            type="password"
            placeholder="再次输入密码"
            class="input-base"
            @keyup.enter="handleRegister"
          >
        </div>

        <button
          :disabled="loading || !form.username || !form.email || !form.password"
          class="btn-primary w-full py-3"
          @click="handleRegister"
        >
          {{ loading ? '注册中...' : '注册' }}
        </button>

        <p class="text-center text-sm text-gray-600">
          已有账号？
          <router-link
            to="/login"
            class="text-cyan-400 hover:text-cyan-300 transition-colors"
          >
            立即登录
          </router-link>
        </p>
      </div>
    </div>
  </div>
</template>