<script setup lang="ts">
import { ref } from 'vue'
import ActivityIcon from '@/components/icons/ActivityIcon.vue'

const wsStatus = ref<'connected' | 'disconnected' | 'reconnecting' | 'connecting'>('disconnected')
const marketData = ref<any[]>([
  { symbol: 'SH000001', name: '上证指数', price: 3256.78, change: 12.34, changePercent: 0.38, volume: '2856亿' },
  { symbol: 'SZ399001', name: '深证成指', price: 10234.56, change: -45.23, changePercent: -0.44, volume: '3521亿' },
  { symbol: 'SZ399006', name: '创业板指', price: 2156.78, change: 8.90, changePercent: 0.41, volume: '1823亿' },
])
</script>

<template>
  <div class="realtime-view space-y-6">
    <div class="flex items-center justify-between">
      <div>
        <h1 class="text-2xl font-bold text-white flex items-center gap-2">
          <ActivityIcon class="w-6 h-6 text-cyan-400" />
          实时行情
        </h1>
        <p class="text-sm text-gray-500 mt-1">A股实时行情 · 自选股 · 告警监控</p>
      </div>
      <div class="flex items-center gap-2">
        <span class="status-dot" :class="{
          'status-dot-online': wsStatus === 'connected',
          'status-dot-offline': wsStatus === 'disconnected',
          'status-dot-warning': wsStatus === 'reconnecting',
        }"></span>
        <span class="text-xs text-gray-500 capitalize">{{ wsStatus }}</span>
        <button class="btn-secondary text-xs py-1.5 px-3 ml-2" @click="wsStatus = 'connecting'">
          {{ wsStatus === 'connected' ? '已连接' : '连接行情' }}
        </button>
      </div>
    </div>

    <!-- 指数卡片 -->
    <div class="grid grid-cols-1 md:grid-cols-3 gap-4">
      <div v-for="item in marketData" :key="item.symbol"
           class="card group cursor-default">
        <div class="flex items-start justify-between mb-3">
          <div>
            <p class="font-mono text-gold-400/80 text-xs">{{ item.symbol }}</p>
            <p class="font-semibold mt-0.5">{{ item.name }}</p>
          </div>
          <span :class="item.changePercent >= 0 ? 'badge-success' : 'badge-danger'"
                class="text-[10px]">
            {{ item.changePercent >= 0 ? '+' : '' }}{{ item.changePercent.toFixed(2) }}%
          </span>
        </div>

        <div class="text-3xl font-bold font-mono mb-2"
             :class="item.change >= 0 ? 'text-emerald-400' : 'text-red-400'">
          {{ item.price.toFixed(2) }}
          <span class="text-base ml-1">{{ item.change >= 0 ? '+' : '' }}{{ item.change.toFixed(2) }}</span>
        </div>

        <div class="flex items-center justify-between text-xs text-gray-600">
          <span>成交量 {{ item.volume }}</span>
          <span>实时</span>
        </div>
      </div>
    </div>

    <!-- K 线图占位 -->
    <div class="card min-h-[450px] flex flex-col">
      <div class="flex items-center justify-between mb-4">
        <h3 class="font-semibold">上证指数 K 线</h3>
        <div class="flex gap-1">
          <button v-for="period in ['分时', '日K', '周K', '月K']" :key="period"
                  class="px-3 py-1 rounded-lg text-xs transition-colors"
                  :class="period === '日K' ? 'bg-cyan-400/10 text-cyan-400' : 'text-gray-500 hover:text-gray-300 hover:bg-white/[0.04]'">
            {{ period }}
          </button>
        </div>
      </div>
      <div class="flex-1 min-h-[350px] bg-surface-dark/50 rounded-xl border border-white/[0.03] flex items-center justify-center">
        <p class="text-gray-600">K 线图表区域（ECharts / TradingView 集成）</p>
      </div>
    </div>
  </div>
</template>