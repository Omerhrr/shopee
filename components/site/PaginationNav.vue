<script setup lang="ts">
const props = defineProps<{ page: number; pages: number }>()
const emit = defineEmits<{ (e: 'go', p: number): void }>()

const windowed = computed(() => {
  const w: (number | '…')[] = []
  const { page, pages } = props
  const push = (n: number | '…') => w.push(n)
  if (pages <= 7) {
    for (let i = 1; i <= pages; i++) push(i)
  } else {
    push(1)
    if (page > 3) push('…')
    for (let i = Math.max(2, page - 1); i <= Math.min(pages - 1, page + 1); i++) push(i)
    if (page < pages - 2) push('…')
    push(pages)
  }
  return w
})
</script>

<template>
  <nav v-if="pages > 1" class="flex items-center justify-center gap-1.5 mt-8" aria-label="Pagination">
    <button class="btn-secondary !px-3 !py-2 text-sm" :disabled="page <= 1" @click="emit('go', page - 1)">←</button>
    <template v-for="(w, i) in windowed" :key="`${w}-${i}`">
      <span v-if="w === '…'" class="px-1.5 text-ink-400">…</span>
      <button
        v-else
        class="min-w-[36px] h-9 rounded-lg text-sm font-semibold border transition"
        :class="w === page ? 'bg-brand-600 border-brand-600 text-white' : 'bg-surface border-ink-200 text-ink-600 hover:bg-ink-50'"
        @click="emit('go', w)"
      >{{ w }}</button>
    </template>
    <button class="btn-secondary !px-3 !py-2 text-sm" :disabled="page >= pages" @click="emit('go', page + 1)">→</button>
  </nav>
</template>
