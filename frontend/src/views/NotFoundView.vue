<script setup lang="ts">
import { RouterLink } from 'vue-router'
</script>

<template>
  <div class="min-h-[60vh] flex items-center justify-center -mt-16">
    <div class="text-center px-4">
      <h1 class="text-[120px] font-black text-gradient-gold leading-none">
        404
      </h1>
      <p class="text-xl text-gray-400 mt-2 mb-2">
        页面不存在
      </p>
      <p class="text-sm text-gray-600 mb-8">
        您访问的页面可能已被删除或地址有误
      </p>
      <RouterLink
        to="/"
        class="btn-primary inline-flex items-center gap-2"
      >
        返回首页
        <svg
          class="w-4 h-4"
          fill="none"
          viewBox="0 0 24 24"
          stroke-width="2"
          stroke="currentColor"
        >
          <path
            stroke-linecap="round"
            stroke-linejoin="round"
            d="M13.5 4.5 21 12m0 0-7.5 7.5M21 12H3"
          />
        </svg>
      </RouterLink>
    </div>
  </div>
</template>