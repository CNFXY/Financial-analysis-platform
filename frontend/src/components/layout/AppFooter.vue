<script setup lang="ts">
import { ref } from 'vue'
import { RouterLink } from 'vue-router'
import { storeToRefs } from 'pinia'
import { useSiteStore } from '@/stores/site'

const year = ref(new Date().getFullYear())
const siteStore = useSiteStore()
const { config } = storeToRefs(siteStore)
</script>

<template>
  <footer class="relative z-10 border-t border-white/[0.04] px-6 py-4">
    <div class="flex flex-col gap-2 text-xs text-gray-600 sm:flex-row sm:items-center sm:justify-between">
      <p>
        &copy; {{ year }} {{ config.site_name }}
        <template v-if="config.icp_beian">
          · <a href="https://beian.miit.gov.cn/" target="_blank" rel="noopener" class="hover:text-gold-400">{{ config.icp_beian }}</a>
        </template>
        <template v-if="config.company_name">
          · {{ config.company_name }}
        </template>
      </p>
      <div class="flex flex-wrap items-center gap-4">
        <span class="flex items-center gap-1">
          <span class="h-1.5 w-1.5 animate-pulse rounded-full bg-emerald-400"></span>
          系统运行正常
        </span>
        <RouterLink to="/disclaimer" class="transition-colors hover:text-gold-400">免责声明</RouterLink>
        <RouterLink to="/privacy" class="transition-colors hover:text-gold-400">隐私政策</RouterLink>
        <RouterLink to="/refund" class="transition-colors hover:text-gold-400">退款政策</RouterLink>
        <RouterLink to="/about" class="transition-colors hover:text-gold-400">关于我们</RouterLink>
      </div>
    </div>
  </footer>
</template>
