<script setup lang="ts">
import { ref } from 'vue'

const activeSection = ref<'overview' | 'users' | 'config' | 'monitor'>('overview')
const systemMetrics = ref({
  cpu: 23, memory: 45, requests: 12847, uptime: '72h 35m',
})
</script>

<template>
  <div class="admin-view space-y-6">
    <div>
      <h1 class="text-2xl font-bold text-white">
        系统管理
      </h1>
      <p class="text-sm text-gray-500 mt-1">
        用户管理 · 系统配置 · 监控告警
      </p>
    </div>

    <!-- 管理导航 -->
    <div class="flex gap-2 flex-wrap">
      <button
        v-for="s in ['overview', 'users', 'config', 'monitor']"
        :key="s"
        class="px-4 py-2 rounded-lg text-sm transition-all"
        :class="activeSection === s
          ? 'bg-gold-400/10 text-gold-400 border border-gold-400/20'
          : 'text-gray-500 hover:bg-white/[0.04] hover:text-gray-300'"
        @click="(activeSection as any) = s"
      >
        {{ { overview: '系统概览', users: '用户管理', config: '系统配置', monitor: '监控中心' }[s] }}
      </button>
    </div>

    <!-- 系统概览 -->
    <div
      v-if="activeSection === 'overview'"
      class="grid grid-cols-2 lg:grid-cols-4 gap-4"
    >
      <div class="card">
        <p class="text-xs text-gray-500 mb-1">
          CPU 使用率
        </p>
        <div class="flex items-end gap-2">
          <span class="text-3xl font-bold font-mono">{{ systemMetrics.cpu }}%</span>
          <span class="text-emerald-400 text-sm mb-1">正常</span>
        </div>
        <div class="mt-2 h-1.5 bg-surface-dark rounded-full overflow-hidden">
          <div
            class="h-full bg-gradient-to-r from-cyan-400 to-emerald-400 rounded-full"
            :style="{ width: systemMetrics.cpu + '%' }"
          />
        </div>
      </div>

      <div class="card">
        <p class="text-xs text-gray-500 mb-1">
          内存使用率
        </p>
        <div class="flex items-end gap-2">
          <span class="text-3xl font-bold font-mono">{{ systemMetrics.memory }}%</span>
          <span class="text-gold-400 text-sm mb-1">中等</span>
        </div>
        <div class="mt-2 h-1.5 bg-surface-dark rounded-full overflow-hidden">
          <div
            class="h-full bg-gradient-to-r from-gold-400 to-amber-400 rounded-full"
            :style="{ width: systemMetrics.memory + '%' }"
          />
        </div>
      </div>

      <div class="card">
        <p class="text-xs text-gray-500 mb-1">
          累计请求
        </p>
        <p class="text-3xl font-bold font-mono text-white">
          {{ systemMetrics.requests.toLocaleString() }}
        </p>
        <p class="text-xs text-gray-600 mt-2">
          今日 API 调用次数
        </p>
      </div>

      <div class="card">
        <p class="text-xs text-gray-500 mb-1">
          运行时间
        </p>
        <p class="text-3xl font-bold font-mono text-white">
          {{ systemMetrics.uptime }}
        </p>
        <p class="text-xs text-gray-600 mt-2">
          服务持续运行
        </p>
      </div>
    </div>

    <!-- 占位提示 -->
    <div
      v-if="activeSection !== 'overview'"
      class="card min-h-[300px] flex items-center justify-center"
    >
      <p class="text-gray-600">
        {{ { users: '用户管理表格（CRUD + RBAC）', config: '系统配置编辑器', monitor: 'Prometheus / Grafana 集成' }[activeSection] }} 开发中...
      </p>
    </div>
  </div>
</template>