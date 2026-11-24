<script setup lang="ts">
defineProps<{ title: string; sub?: string }>()
</script>

<template>
  <div class="mb-6">
    <h2 class="text-xl md:text-2xl font-extrabold text-ink-900">{{ title }}</h2>
    <p v-if="sub" class="text-sm text-ink-500 mt-1">{{ sub }}</p>
  </div>
</template>
