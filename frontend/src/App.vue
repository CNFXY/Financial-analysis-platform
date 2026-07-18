<script setup lang="ts">
import { RouterView } from 'vue-router'
import AppLayout from '@/layouts/AppLayout.vue'
</script>

<template>
  <AppLayout>
    <RouterView v-slot="{ Component }">
      <transition
        name="page-fade"
        mode="out-in"
      >
        <component :is="Component" />
      </transition>
    </RouterView>
  </AppLayout>
</template>

<style>
.page-fade-enter-active,
.page-fade-leave-active {
  transition: opacity 0.25s ease;
}
.page-fade-enter-from,
.page-fade-leave-to {
  opacity: 0;
}
</style>
