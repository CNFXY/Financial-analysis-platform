<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'

const router = useRouter()
const counters = ref({ indicators: 0, models: 0, accuracy: 0, realtime: 0 })
const isLoaded = ref(false)

function animateCounters() {
  const targets = { indicators: 15, models: 6, accuracy: 99, realtime: 24 }
  const duration = 2000
  const start = Date.now()

  function tick() {
    const elapsed = Date.now() - start
    const progress = Math.min(elapsed / duration, 1)
    // Ease out cubic
    const ease = 1 - Math.pow(1 - progress, 3)

    counters.value = {
      indicators: Math.round(targets.indicators * ease),
      models: Math.round(targets.models * ease),
      accuracy: Math.round(targets.accuracy * ease),
      realtime: Math.round(targets.realtime * ease),
    }

    if (progress < 1) {
      requestAnimationFrame(tick)
    } else {
      isLoaded.value = true
    }
  }

  tick()
}

onMounted(() => {
  setTimeout(animateCounters, 300)
})
</script>

<template>
  <div class="home-view relative min-h-[calc(100vh-10rem)] flex items-center justify-center -mt-8">
    <!-- Hero 区域 -->
    <div class="text-center max-w-4xl mx-auto px-4">
      <!-- 版本徽章 -->
      <div
        class="inline-flex items-center gap-2 px-4 py-2 rounded-full text-sm font-medium
               bg-gold-400/10 text-gold-400 border border-gold-400/20 mb-8
               shadow-lg shadow-gold-400/5 animate-fade-in-up"
        style="animation-delay: 100ms"
      >
        <span class="w-1.5 h-1.5 rounded-full bg-gold-400 animate-pulse"></span>
        v5.0 全栈升级 · Vue 3 + TypeScript + Tailwind CSS
      </div>

      <!-- 主标题 -->
      <h1 class="text-4xl md:text-5xl lg:text-6xl font-black leading-tight mb-6 animate-fade-in-up"
          style="animation-delay: 200ms">
        <span class="text-white">智能基金估算</span>
        <br />
        <span class="text-gradient-gold">&amp; 组合分析</span>
      </h1>

      <!-- 副标题 -->
      <p class="text-base md:text-lg text-gray-500 max-w-2xl mx-auto mb-12 leading-relaxed animate-fade-in-up"
         style="animation-delay: 350ms">
        基于多模型预测引擎 · 支持中国公募 / A股 / 海外基金<br class="hidden sm:block" />
        实时净值估算与收益分析
      </p>

      <!-- 核心数据指标 -->
      <div class="grid grid-cols-2 md:grid-cols-4 gap-3 md:gap-6 max-w-3xl mx-auto mb-14 animate-fade-in-up"
           style="animation-delay: 450ms">
        <div v-for="(value, key) in counters" :key="key"
             class="group relative px-4 py-5 rounded-2xl bg-surface/50 backdrop-blur-xl
                    border border-white/[0.06] transition-all duration-300
                    hover:border-gold-400/15 hover:-translate-y-1 hover:shadow-lg hover:shadow-gold-400/5">
          <div class="text-3xl md:text-4xl font-bold font-mono text-gradient-gold">
            {{ value }}
            <span class="text-base" v-if="key === 'accuracy'">%</span>
            <span class="text-base" v-else-if="key === 'realtime'">h</span>
          </div>
          <div class="text-xs md:text-sm text-gray-600 mt-1.5 uppercase tracking-wider font-mono">
            {{ { indicators: '技术指标', models: '分析模型', accuracy: '准确率', realtime: '实时更新' }[key] }}
          </div>
        </div>
      </div>

      <!-- CTA 按钮组 -->
      <div class="flex flex-col sm:flex-row items-center justify-center gap-4 animate-fade-in-up"
           style="animation-delay: 550ms">
        <router-link to="/fund-estimate" class="btn-primary inline-flex items-center gap-2 text-base px-8 py-3.5">
          开始估算
          <svg class="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke-width="2" stroke="currentColor">
            <path stroke-linecap="round" stroke-linejoin="round" d="M13.5 4.5 21 12m0 0-7.5 7.5M21 12H3" />
          </svg>
        </router-link>
        <router-link to="/realtime" class="btn-secondary inline-flex items-center gap-2 text-base px-8 py-3.5">
          <svg class="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke-width="1.5" stroke="currentColor">
            <path stroke-linecap="round" stroke-linejoin="round" d="M3.75 3v11.25A2.25 2.25 0 0 0 6 16.5h2.25M3.75 3h-1.5m1.5 0h16.5m0 0h1.5m-1.5 0v11.25A2.25 2.25 0 0 1 18 16.5h-2.25m-7.5 0h7.5m-7.5 0-1 3m8.5-3 1 3m0 0 .5 1.5m-.5-1.5h-9.5m0 0-.5 1.5M9 11.25v1.5M12 9v3.75m3-6v6" />
          </svg>
          实时行情
        </router-link>
      </div>

      <!-- 技术栈展示 -->
      <div class="mt-16 pt-8 border-t border-white/[0.04] animate-fade-in-up" style="animation-delay: 700ms">
        <p class="text-xs text-gray-600 uppercase tracking-[0.2em] mb-4">技术架构</p>
        <div class="flex flex-wrap items-center justify-center gap-x-6 gap-y-2 text-xs text-gray-500">
          <span class="flex items-center gap-1.5"><span class="status-dot-online"></span>Vue 3 + Vite</span>
          <span class="flex items-center gap-1.5"><span class="status-dot-online"></span>TypeScript 5.7</span>
          <span class="flex items-center gap-1.5"><span class="status-dot-online"></span>Tailwind CSS 3.4</span>
          <span class="flex items-center gap-1.5"><span class="status-dot-online"></span>Pinia 状态管理</span>
          <span class="flex items-center gap-1.5"><span class="status-dot-online"></span>ECharts 可视化</span>
          <span class="flex items-center gap-1.5"><span class="status-dot-online"></span>RESTful API</span>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
@keyframes fadeInUp {
  from { opacity: 0; transform: translateY(20px); }
  to { opacity: 1; transform: translateY(0); }
}
.animate-fade-in-up {
  animation: fadeInUp 0.7s ease-out both;
}
</style>
