<script setup lang="ts">
const reports = ref([
  { id: 'r1', title: '市场概览日报', type: 'daily', date: '2026-07-15', status: 'ready' },
  { id: 'r2', title: '组合分析报告 #1', type: 'portfolio', date: '2026-07-14', status: 'ready' },
  { id: 'r3', title: '周度复盘报告', type: 'weekly', date: '2026-07-13', status: 'processing' },
])
</script>

<template>
  <div class="report-view space-y-6">
    <div class="flex items-center justify-between">
      <div>
        <h1 class="text-2xl font-bold text-white">
          报告中心
        </h1>
        <p class="text-sm text-gray-500 mt-1">
          日报、组合分析报告、Excel 导出
        </p>
      </div>
      <button class="btn-primary text-sm py-2 px-5">
        生成今日报告
      </button>
    </div>

    <!-- 报告列表 -->
    <div class="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
      <div
        v-for="report in reports"
        :key="report.id"
        class="card group cursor-pointer hover:border-gold-400/20"
      >
        <div class="flex items-start justify-between mb-3">
          <span
            :class="report.type === 'daily' ? 'badge-gold'
              : report.type === 'portfolio' ? 'badge-cyan' : 'badge-success'"
            class="capitalize text-[10px]"
          >
            {{ report.type === 'daily' ? '日报' : report.type === 'portfolio' ? '组合' : '周报' }}
          </span>
          <span
            class="flex items-center gap-1.5 text-xs"
            :class="report.status === 'ready' ? 'text-emerald-400' : 'text-gold-400'"
          >
            <span
              class="w-1.5 h-1.5 rounded-full animate-pulse"
              :class="report.status === 'ready' ? 'bg-emerald-400' : 'bg-gold-400'"
            />
            {{ report.status === 'ready' ? '就绪' : '生成中' }}
          </span>
        </div>
        <h3 class="font-semibold mb-2 group-hover:text-gold-400 transition-colors">
          {{ report.title }}
        </h3>
        <div class="flex items-center justify-between text-xs text-gray-600">
          <span>{{ report.date }}</span>
          <div class="opacity-0 group-hover:opacity-100 transition-opacity flex gap-2">
            <button class="hover:text-cyan-400 transition-colors">
              预览
            </button>
            <button class="hover:text-emerald-400 transition-colors">
              下载
            </button>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>