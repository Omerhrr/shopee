<script setup lang="ts">
// Admin shell: sidebar + content area (no storefront header/footer)
</script>

<template>
  <div class="min-h-screen bg-ink-50">
    <AdminSidebar>
      <slot />
    </AdminSidebar>
  </div>
</template>
