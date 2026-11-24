<script setup lang="ts">
const props = defineProps<{ product: any }>()
const { t, tr, locale } = useI18n()
const money = useMoney()
const cart = useCartStore()
const added = ref(false)

const pendingTranslation = computed(
  () => locale.value === 'en' && props.product.original_lang === 'ko' && props.product.translation_status !== 'done'
)

const add = () => {
  cart.add(props.product)
  added.value = true
  setTimeout(() => (added.value = false), 1200)
}
</script>

<template>
  <div class="card overflow-hidden group flex flex-col hover:shadow-pop transition">
    <NuxtLink :to="`/products/${product.slug}`" class="block relative overflow-hidden">
      <div class="aspect-square bg-ink-100">
        <SmartImage :src="product.images && product.images.length ? product.images[0] : null" :alt="tr(product, 'title')" class="w-full h-full object-cover group-hover:scale-105 transition duration-300" />
      </div>
      <span v-if="pendingTranslation" class="badge bg-amber-100 text-amber-800 dark:bg-amber-500/15 dark:text-amber-300 absolute top-2 left-2">{{ t('product.translationPending') }}</span>
    </NuxtLink>
    <div class="p-4 flex flex-col flex-1">
      <NuxtLink :to="`/products/${product.slug}`" class="text-sm font-semibold text-ink-800 leading-snug hover:text-brand-700 line-clamp-2">
        {{ tr(product, 'title') }}
      </NuxtLink>
      <div class="mt-1.5 flex items-center gap-1 text-xs text-ink-400">
        <span class="text-amber-500">★</span>
        <span>{{ product.rating.toFixed(1) }}</span>
        <span>·</span>
        <span>{{ t('product.reviews', { n: product.reviews }) }}</span>
      </div>
      <div class="mt-auto pt-3 flex items-center justify-between gap-2">
        <span class="text-lg font-extrabold text-ink-900">{{ money(product.price_sell) }}</span>
        <button class="btn-primary !px-3 !py-2 text-xs" :aria-label="t('product.addCart')" @click.stop="add">
          <svg v-if="!added" style="width:16px;height:16px" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path d="M6 6h15l-1.5 9h-12L5 3H2" /><circle cx="9" cy="20" r="1.6" /><circle cx="18" cy="20" r="1.6" /></svg>
          <svg v-else style="width:16px;height:16px" fill="none" stroke="currentColor" stroke-width="2.5" viewBox="0 0 24 24"><path d="m5 13 4 4L19 7" /></svg>
        </button>
      </div>
    </div>
  </div>
</template>
