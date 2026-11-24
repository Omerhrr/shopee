<script setup lang="ts">
/**
 * Image with a built-in fallback: if the source is missing or fails to load,
 * the local placeholder graphic is shown instead of a broken image icon.
 */
const props = defineProps<{ src?: string | null; alt?: string; eager?: boolean }>()
const errored = ref(false)
const display = computed(() => (!props.src || errored.value) ? '/placeholder.svg' : props.src)
</script>

<template>
  <img
    :src="display"
    :alt="alt || ''"
    :loading="eager ? 'eager' : 'lazy'"
    class="w-full h-full object-cover"
    @error="errored = true"
  />
</template>
