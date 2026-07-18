<script setup lang="ts">
defineProps<{ title: string; updated?: string }>()
</script>

<template>
  <div class="mx-auto w-full max-w-3xl px-4 py-8 md:py-12">
    <header class="mb-8 border-b border-white/[0.06] pb-5">
      <h1 class="text-2xl font-bold text-gold-400 md:text-3xl">{{ title }}</h1>
      <p v-if="updated" class="mt-2 text-sm text-gray-500">最后更新：{{ updated }}</p>
    </header>
    <article class="prose-legal">
      <slot />
    </article>
  </div>
</template>

<style scoped>
.prose-legal {
  color: #d1d5db;
  line-height: 1.75;
  font-size: 0.95rem;
}
.prose-legal h2 {
  margin: 2rem 0 0.75rem;
  font-size: 1.125rem;
  font-weight: 600;
  color: #f3f4f6;
}
.prose-legal h3 {
  margin: 1.5rem 0 0.5rem;
  font-size: 1rem;
  font-weight: 600;
  color: #e5e7eb;
}
.prose-legal p {
  margin-bottom: 0.85rem;
}
.prose-legal ul {
  margin: 0 0 0.85rem;
  padding-left: 1.4rem;
  list-style: disc;
}
.prose-legal ol {
  margin: 0 0 0.85rem;
  padding-left: 1.4rem;
  list-style: decimal;
}
.prose-legal li {
  margin-bottom: 0.35rem;
}
.prose-legal strong {
  color: #ffd94d;
  font-weight: 600;
}
.prose-legal a {
  color: #f0b020;
  text-decoration: underline;
}
.prose-legal code {
  background: rgba(240, 176, 32, 0.08);
  padding: 0.1rem 0.35rem;
  border-radius: 0.25rem;
  font-size: 0.875em;
  color: #ffe580;
}
</style>
