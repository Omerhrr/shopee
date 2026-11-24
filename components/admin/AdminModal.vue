<script setup lang="ts">
const props = defineProps<{ open: boolean; title: string; wide?: boolean }>()
const emit = defineEmits<{ (e: 'close'): void }>()
</script>

<template>
  <Teleport to="body">
    <div v-if="open" class="fixed inset-0 z-50 flex items-center justify-center p-4">
      <div class="absolute inset-0 bg-inverse/50 backdrop-blur-sm" @click="emit('close')" />
      <div class="relative bg-surface rounded-2xl shadow-pop w-full p-6 max-h-[88vh] overflow-y-auto scroll-thin" :class="wide ? 'max-w-3xl' : 'max-w-lg'">
        <div class="flex items-center justify-between mb-5">
          <h3 class="text-lg font-extrabold text-ink-900">{{ title }}</h3>
          <button class="btn-ghost" aria-label="Close" @click="emit('close')">✕</button>
        </div>
        <slot />
      </div>
    </div>
  </Teleport>
</template>
