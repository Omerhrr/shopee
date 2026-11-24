<script setup lang="ts">
// Global page-title template: append the (theme-managed) site name unless the
// page title already contains it. Prevents "Shopee · Dashboard · Shopee".
const { siteName } = useTheme()
useHead({
  titleTemplate: (chunk?: string) => {
    const name = siteName.value || 'Shopee'
    if (!chunk) return name
    return chunk.includes(name) ? chunk : `${chunk} · ${name}`
  }
})
</script>

<template>
  <div class="min-h-screen flex flex-col">
    <NuxtLayout>
      <NuxtPage />
    </NuxtLayout>
    <Toast />
  </div>
</template>
