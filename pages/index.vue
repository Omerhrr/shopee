<script setup lang="ts">
const api = useApi()
const { t, tr } = useI18n()
const money = useMoney()

const { data: home, pending } = await useAsyncData('home', async () => await api('/catalog/home'))

useHead({ title: () => `${home.value?.site_name || 'Shopee'} · ${t('home.heroBadge')}` })
</script>

<template>
  <div>
    <!-- Hero -->
    <section class="bg-gradient-to-br from-brand-100/60 via-surface to-accent-100/60 border-b border-ink-100">
      <div class="max-w-7xl mx-auto px-4 py-14 md:py-20 text-center">
        <span class="badge bg-brand-100 text-brand-800 mb-4">{{ t('home.heroBadge') }}</span>
        <h1 class="text-3xl md:text-5xl font-extrabold text-ink-900 tracking-tight max-w-3xl mx-auto leading-tight">
          {{ t('home.heroTitle') }}
        </h1>
        <p class="mt-4 text-ink-500 max-w-2xl mx-auto md:text-lg">{{ t('home.heroSubtitle') }}</p>
        <div class="mt-7 flex flex-wrap items-center justify-center gap-3">
          <NuxtLink to="/products" class="btn-primary text-base !px-7 !py-3">{{ t('home.shopNow') }}</NuxtLink>
          <a href="#categories" class="btn-secondary text-base !px-7 !py-3">{{ t('home.browseCategories') }}</a>
        </div>
        <div class="mt-8 flex flex-wrap justify-center gap-x-8 gap-y-2 text-sm text-ink-500 font-medium">
          <span class="flex items-center gap-1.5"><span class="text-accent-600">●</span>{{ t('home.trustScraped') }}</span>
          <span class="flex items-center gap-1.5"><span class="text-accent-600">●</span>{{ t('home.trustTranslated') }}</span>
          <span class="flex items-center gap-1.5"><span class="text-accent-600">●</span>{{ t('home.trustWholesale') }}</span>
        </div>
      </div>
    </section>

    <div class="max-w-7xl mx-auto px-4 py-10 space-y-14">
      <!-- Categories -->
      <section id="categories">
        <SectionTitle :title="t('home.browseCategories')" />
        <div class="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-6 gap-3">
          <NuxtLink
            v-for="c in home?.categories || []"
            :key="c.slug"
            :to="`/products?category=${c.slug}`"
            class="card !rounded-xl px-4 py-5 text-center hover:border-brand-300 hover:shadow-pop transition group"
          >
            <div class="text-sm font-bold text-ink-800 group-hover:text-brand-700">{{ tr(c, 'name') }}</div>
          </NuxtLink>
        </div>
      </section>

      <!-- Featured -->
      <section>
        <div class="flex items-end justify-between">
          <SectionTitle :title="t('home.featured')" />
          <NuxtLink to="/products?sort=popular" class="text-sm font-semibold text-brand-700 hover:text-brand-800 mb-6">{{ t('home.viewAll') }} →</NuxtLink>
        </div>
        <div v-if="pending" class="text-ink-400 text-sm py-10 text-center">{{ t('products.loading') }}</div>
        <div class="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-4">
          <ProductCard v-for="p in home?.featured || []" :key="p.slug" :product="p" />
        </div>
      </section>

      <!-- Newest -->
      <section>
        <div class="flex items-end justify-between">
          <SectionTitle :title="t('home.newest')" />
          <NuxtLink to="/products" class="text-sm font-semibold text-brand-700 hover:text-brand-800 mb-6">{{ t('home.viewAll') }} →</NuxtLink>
        </div>
        <div class="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-4">
          <ProductCard v-for="p in home?.newest || []" :key="p.slug" :product="p" />
        </div>
      </section>
    </div>
  </div>
</template>
