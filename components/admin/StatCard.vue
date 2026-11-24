<script setup lang="ts">
defineProps<{ label: string; value: string; hint?: string; accent?: 'brand' | 'green' | 'red' | 'plain' }>()
</script>

<template>
  <div class="card p-5">
    <div class="text-xs font-bold uppercase tracking-wider text-ink-400">{{ label }}</div>
    <div
      class="mt-2 text-2xl font-extrabold"
      :class="accent === 'brand' ? 'text-brand-700' : accent === 'green' ? 'text-emerald-600' : accent === 'red' ? 'text-rose-600' : 'text-ink-900'"
    >{{ value }}</div>
    <div v-if="hint" class="text-xs text-ink-400 mt-1">{{ hint }}</div>
  </div>
</template>
