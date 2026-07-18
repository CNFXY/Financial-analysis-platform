<script setup lang="ts">
import { ref, computed } from 'vue'
// TODO: 集成 portfolioApi

const activeTab = ref<'overview' | 'holdings' | 'analysis'>('overview')
const totalValue = ref(125678.90)
const totalCost = ref(108000.00)
const totalProfit = computed(() => totalValue.value - totalCost.value)
const totalProfitRate = computed(() => ((totalProfit.value / totalCost.value) * 100).toFixed(2))

const holdings = ref([
  { fundCode: '510300', name: '华泰柏瑞沪深300ETF', shares: 10000, costPrice: 3.8, currentNav: 4.12, profit: 3200, profitRate: 8.42, weight: 32 },
  { fundCode: '110011', name: '易方达中小盘混合', shares: 5000, costPrice: 9.2, currentNav: 8.77, profit: -2150, profitRate: -4.67, weight: 35 },
  { fundCode: '161725', name: '招商中证白酒指数', shares: 2000, costPrice: 1.05, currentNav: 0.98, profit: -140, profitRate: -6.67, weight: 15 },
  { fundCode: '000001', name: '华夏成长混合', shares: 8000, costPrice: 2.5, currentNav: 2.68, profit: 1440, profitRate: 7.20, weight: 18 },
])
</script>

<template>
  <div class="portfolio-view space-y-6">
    <div>
      <h1 class="text-2xl font-bold text-white">组合分析</h1>
      <p class="text-sm text-gray-500 mt-1">投资组合收益分析、风险评估与资产配置</p>
    </div>

    <!-- 总览卡片 -->
    <div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
      <div class="card">
        <p class="text-xs text-gray-500 uppercase tracking-wider mb-1">总市值</p>
        <p class="text-2xl font-bold font-mono text-white">&yen;{{ totalValue.toLocaleString('zh-CN', { minimumFractionDigits: 2 }) }}</p>
      </div>
      <div class="card">
        <p class="text-xs text-gray-500 uppercase tracking-wider mb-1">总成本</p>
        <p class="text-2xl font-bold font-mono text-gray-400">&yen;{{ totalCost.toLocaleString('zh-CN', { minimumFractionDigits: 2 }) }}</p>
      </div>
      <div class="card" :class="{ '!border-emerald-400/15': Number(totalProfitRate) >= 0 }">
        <p class="text-xs text-gray-500 uppercase tracking-wider mb-1">累计盈亏</p>
        <p class="text-2xl font-bold font-mono" :class="Number(totalProfitRate) >= 0 ? 'text-emerald-400' : 'text-red-400'">
          {{ Number(totalProfitRate) >= 0 ? '+' : '' }}&yen;{{ totalProfit.toFixed(2) }}
        </p>
      </div>
      <div class="card">
        <p class="text-xs text-gray-500 uppercase tracking-wider mb-1">收益率</p>
        <p class="text-2xl font-bold font-mono" :class="Number(totalProfitRate) >= 0 ? 'text-emerald-400' : 'text-red-400'">
          {{ Number(totalProfitRate) >= 0 ? '+' : '' }}{{ totalProfitRate }}%
        </p>
      </div>
    </div>

    <!-- Tab 切换 -->
    <div class="flex gap-1 p-1 bg-surface-light/30 rounded-xl w-fit">
      <button v-for="tab in ['overview', 'holdings', 'analysis']" :key="tab"
              class="px-4 py-2 rounded-lg text-sm font-medium transition-all"
              :class="activeTab === tab
                ? 'bg-gold-400/10 text-gold-400 shadow-sm'
                : 'text-gray-500 hover:text-gray-300'"
              @click="(activeTab as any) = tab">
        {{ { overview: '总览', holdings: '持仓明细', analysis: '风险分析' }[tab] }}
      </button>
    </div>

    <!-- 持仓表格 -->
    <div v-if="activeTab === 'holdings'" class="card overflow-hidden !p-0">
      <table class="table-data">
        <thead><tr>
          <th>基金代码</th><th>名称</th><th class="text-right">持有份额</th>
          <th class="text-right">成本价</th><th class="text-right">当前净值</th>
          <th class="text-right">盈亏金额</th><th class="text-right">盈亏比例</th><th>权重</th>
        </tr></thead>
        <tbody>
          <tr v-for="h in holdings" :key="h.fundCode">
            <td class="font-mono text-gold-400/80">{{ h.fundCode }}</td>
            <td>{{ h.name }}</td>
            <td class="text-right font-mono">{{ h.shares.toLocaleString() }}</td>
            <td class="text-right font-mono">{{ h.costPrice.toFixed(3) }}</td>
            <td class="text-right font-mono">{{ h.currentNav?.toFixed(4) ?? '-' }}</td>
            <td class="text-right font-mono" :class="h.profit >= 0 ? 'text-emerald-400' : 'text-red-400'">
              {{ (h.profit >= 0 ? '+' : '') + h.profit.toFixed(2) }}
            </td>
            <td class="text-right font-mono" :class="h.profitRate >= 0 ? 'text-emerald-400' : 'text-red-400'">
              {{ (h.profitRate >= 0 ? '+' : '') + h.profitRate.toFixed(2) }}%
            </td>
            <td class="text-center"><span class="badge badge-gold">{{ h.weight }}%</span></td>
          </tr>
        </tbody>
      </table>
    </div>

    <!-- 分析图表占位 -->
    <div v-if="activeTab === 'analysis'" class="card min-h-[400px] flex items-center justify-center">
      <p class="text-gray-600">风险分析图表（ECharts 集成区域）</p>
      <!-- TODO: 集成 ECharts 组件 -->
    </div>
  </div>
</template>
