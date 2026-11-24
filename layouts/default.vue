<script setup lang="ts">
// Sticky footer layout for the storefront
const { t } = useI18n()
</script>

<template>
  <div class="min-h-screen flex flex-col bg-surface">
    <SiteHeader />
    <main class="flex-1">
      <slot />
    </main>
    <SiteFooter />
  </div>
</template>
