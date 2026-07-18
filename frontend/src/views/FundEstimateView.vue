<script setup lang="ts">
import { ref } from 'vue'
import { SearchIcon } from '@/components/icons'

const searchKeyword = ref('')
const searchResults = ref<any[]>([])
const isSearching = ref(false)
const selectedCodes = ref<string[]>([])

// Mock 数据 - 实际调用 fundApi.search
async function handleSearch() {
  if (!searchKeyword.value.trim()) return
  isSearching.value = true
  // TODO: 替换为真实 API 调用
  // const res = await fundApi.search(searchKeyword.value)
  // searchResults.value = res.data
  setTimeout(() => {
    searchResults.value = [
      { code: '510300', name: '华泰柏瑞沪深300ETF联接A', type: '股票型', nav: 4.1234, changePercent: 1.23 },
      { code: '110011', name: '易方达中小盘混合', type: '混合型', nav: 8.7654, changePercent: -0.45 },
      { code: '000001', name: '华夏成长混合', type: '混合型', nav: 2.3456, changePercent: 0.87 },
    ]
    isSearching.value = false
  }, 500)
}

function toggleSelect(code: string) {
  const idx = selectedCodes.value.indexOf(code)
  if (idx >= 0) selectedCodes.value.splice(idx, 1)
  else selectedCodes.value.push(code)
}

function formatChange(val: number): string {
  return (val > 0 ? '+' : '') + val.toFixed(2) + '%'
}

function getChangeClass(val: number): string {
  return val > 0 ? 'text-emerald-400' : val < 0 ? 'text-red-400' : 'text-gray-400'
}
</script>

<template>
  <div class="fund-estimate-view space-y-6">
    <!-- 页面标题 -->
    <div class="flex items-center justify-between">
      <div>
        <h1 class="text-2xl font-bold text-white">基金估算</h1>
        <p class="text-sm text-gray-500 mt-1">搜索基金代码或名称，获取实时估值估算</p>
      </div>
      <div v-if="selectedCodes.length > 0" class="text-sm text-gold-400">
        已选 {{ selectedCodes.length }} 只基金
        <button class="ml-3 btn-primary py-1.5 px-4 text-xs">开始估算</button>
      </div>
    </div>

    <!-- 搜索栏 -->
    <div class="card p-4">
      <div class="relative flex items-center gap-3">
        <SearchIcon class="w-5 h-5 absolute left-4 text-gray-500 flex-shrink-0" />
        <input
          v-model="searchKeyword"
          type="text"
          placeholder="输入基金代码（如 510300）或名称关键词..."
          class="input-base pl-12 pr-24"
          @keyup.enter="handleSearch"
        />
        <button
          :disabled="isSearching || !searchKeyword.trim()"
          class="absolute right-2 btn-primary py-2 px-5 text-sm"
          @click="handleSearch"
        >
          {{ isSearching ? '搜索中...' : '搜索' }}
        </button>
      </div>

      <!-- 快捷标签 -->
      <div class="flex gap-2 mt-3 flex-wrap">
        <span class="text-xs text-gray-600 mr-1 self-center">热门：</span>
        <button v-for="code in ['510300', '110011', '000001', '161725']" :key="code"
                class="px-3 py-1 text-xs rounded-lg bg-white/[0.04] border border-white/6
                       text-gray-400 hover:text-gold-400 hover:border-gold-400/20 transition-colors"
                @click="searchKeyword = code; handleSearch()">
          {{ code }}
        </button>
      </div>
    </div>

    <!-- 搜索结果 -->
    <div v-if="searchResults.length > 0" class="card overflow-hidden !p-0">
      <table class="table-data">
        <thead>
          <tr>
            <th class="w-12"></th>
            <th>基金代码</th>
            <th>基金名称</th>
            <th>类型</th>
            <th class="text-right">最新净值</th>
            <th class="text-right">涨跌幅</th>
            <th class="w-20">操作</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="item in searchResults" :key="item.code">
            <td>
              <input type="checkbox" class="rounded bg-transparent border-gray-600"
                     :checked="selectedCodes.includes(item.code)"
                     @change="toggleSelect(item.code)" />
            </td>
            <td class="font-mono text-gold-400/80">{{ item.code }}</td>
            <td>{{ item.name }}</td>
            <td><span class="badge badge-cyan">{{ item.type }}</span></td>
            <td class="text-right font-mono">{{ item.nav?.toFixed(4) ?? '-' }}</td>
            <td class="text-right font-mono" :class="getChangeClass(item.changePercent ?? 0)">
              {{ formatChange(item.changePercent ?? 0) }}
            </td>
            <td class="text-center">
              <button class="btn-ghost text-xs" @click="$router.push(`/fund/${item.code}`)">详情</button>
            </td>
          </tr>
        </tbody>
      </table>
    </div>

    <!-- 空状态 -->
    <div v-else-if="!isSearching && searchKeyword" class="card text-center py-16">
      <p class="text-gray-500">未找到相关基金，请尝试其他关键词</p>
    </div>

    <!-- 初始状态 -->
    <div v-else class="card text-center py-16">
      <svg class="w-12 h-12 mx-auto mb-4 text-gray-700" fill="none" viewBox="0 0 24 24" stroke-width="1.5" stroke="currentColor">
        <path stroke-linecap="round" stroke-linejoin="round" d="m21 21-5.197-5.197m0 0A7.5 7.5 0 1 0 5.196 5.196a7.5 7.5 0 0 0 10.607 10.607Z" />
      </svg>
      <p class="text-gray-500">输入基金代码或名称开始搜索</p>
    </div>
  </div>
</template>