<script setup lang="ts">
const { t } = useI18n()
const { siteName } = useTheme()
const year = new Date().getFullYear()
const letter = computed(() => (siteName.value || 'S').charAt(0).toUpperCase())
</script>

<template>
  <footer class="mt-auto bg-inverse text-ink-300">
    <div class="max-w-7xl mx-auto px-4 py-10 grid grid-cols-1 md:grid-cols-3 gap-8">
      <div>
        <div class="flex items-center gap-2 mb-3">
          <span class="w-8 h-8 rounded-lg bg-brand-600 text-white font-extrabold flex items-center justify-center">{{ letter }}</span>
          <span class="text-lg font-extrabold text-white">{{ siteName }}</span>
        </div>
        <p class="text-sm leading-relaxed">{{ t('footer.tagline') }}</p>
      </div>
      <div>
        <h4 class="text-white font-semibold text-sm mb-3">{{ t('footer.links') }}</h4>
        <ul class="space-y-2 text-sm">
          <li><NuxtLink to="/" class="hover:text-white">{{ t('nav.home') }}</NuxtLink></li>
          <li><NuxtLink to="/products" class="hover:text-white">{{ t('nav.products') }}</NuxtLink></li>
        </ul>
      </div>
      <div>
        <h4 class="text-white font-semibold text-sm mb-3">{{ t('footer.info') }}</h4>
        <ul class="space-y-2 text-sm">
          <li><NuxtLink to="/cart" class="hover:text-white">{{ t('nav.cart') }}</NuxtLink></li>
          <li><NuxtLink to="/admin" class="hover:text-white">{{ t('footer.admin') }}</NuxtLink></li>
        </ul>
      </div>
    </div>
    <div class="border-t border-white/10 py-4 text-center text-xs">{{ t('footer.rights', { year }) }}</div>
  </footer>
</template>
