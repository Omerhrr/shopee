<script setup lang="ts">
const api = useApi()
const { t, tr, locale } = useI18n()
const money = useMoney()
const cart = useCartStore()
const route = useRoute()
const router = useRouter()
const toast = useToastState()

const { data: product, error } = await useAsyncData(`product-${route.params.slug}`, async () =>
  await api(`/catalog/products/${route.params.slug}`)
)

if (error.value || !product.value) {
  throw createError({ statusCode: 404, statusMessage: 'Product not found', fatal: true })
}

const qty = ref(1)
const activeImage = ref(0)
const tab = ref<'description' | 'shipping'>('description')

const pendingTranslation = computed(
  () => locale.value === 'en' && product.value?.original_lang === 'ko' && product.value?.translation_status !== 'done'
)

const desc = computed(() => {
  if (locale.value === 'ko') return product.value?.desc_ko || product.value?.desc_en || ''
  return product.value?.desc_en || product.value?.desc_ko || ''
})

const addToCart = (buy = false) => {
  cart.add(product.value, qty.value)
  if (buy) router.push('/cart')
  else toast(t('product.added'))
}

useHead({
  title: () => tr(product.value, 'title'),
  meta: [{ name: 'description', content: () => desc.value.slice(0, 150) }]
})
</script>

<template>
  <div v-if="product" class="max-w-7xl mx-auto px-4 py-8">
    <nav class="text-sm text-ink-400 mb-5 flex items-center gap-1.5 flex-wrap">
      <NuxtLink to="/" class="hover:text-ink-700">{{ t('nav.home') }}</NuxtLink>
      <span>/</span>
      <NuxtLink to="/products" class="hover:text-ink-700">{{ t('nav.products') }}</NuxtLink>
      <template v-if="product.category">
        <span>/</span>
        <NuxtLink :to="`/products?category=${product.category.slug}`" class="hover:text-ink-700">{{ tr(product.category, 'name') }}</NuxtLink>
      </template>
    </nav>

    <div class="grid md:grid-cols-2 gap-8 lg:gap-12">
      <!-- Gallery -->
      <div>
        <div class="card overflow-hidden aspect-square !rounded-2xl bg-ink-50">
          <SmartImage
            :src="product.images && product.images.length ? product.images[activeImage] : null"
            :alt="tr(product, 'title')"
            eager
          />
        </div>
        <div v-if="product.images && product.images.length > 1" class="flex gap-2 mt-3">
          <button
            v-for="(img, i) in product.images"
            :key="i"
            class="w-16 h-16 rounded-lg overflow-hidden border-2 transition bg-ink-50"
            :class="i === activeImage ? 'border-brand-600' : 'border-transparent opacity-70'"
            @click="activeImage = i"
          >
            <SmartImage :src="img" :alt="`${tr(product, 'title')} ${i + 1}`" />
          </button>
        </div>
      </div>

      <!-- Info -->
      <div>
        <div v-if="pendingTranslation" class="badge bg-amber-100 text-amber-800 mb-3">{{ t('product.translationPending') }}</div>
        <h1 class="text-2xl md:text-3xl font-extrabold text-ink-900 leading-tight">{{ tr(product, 'title') }}</h1>

        <div class="mt-2 flex items-center gap-2 text-sm text-ink-400">
          <span class="text-amber-500 font-bold">★ {{ product.rating.toFixed(1) }}</span>
          <span>·</span>
          <span>{{ t('product.reviews', { n: product.reviews }) }}</span>
          <span>·</span>
          <span class="text-emerald-600 font-semibold">{{ product.stock_status === 'in_stock' ? t('product.inStock') : t('product.outOfStock') }}</span>
        </div>

        <div class="mt-5 flex items-baseline gap-3">
          <span class="text-3xl md:text-4xl font-extrabold text-brand-700">{{ money(product.price_sell) }}</span>
        </div>
        <p class="mt-1 text-xs text-ink-400">{{ t('product.fromKorea') }}</p>

        <div class="mt-6 flex items-center gap-3">
          <div>
            <span class="label">{{ t('product.quantity') }}</span>
            <div class="flex items-center border border-ink-200 rounded-lg overflow-hidden">
              <button class="w-10 h-11 hover:bg-ink-50 font-bold text-ink-500" @click="qty = Math.max(1, qty - 1)">−</button>
              <input v-model.number="qty" class="w-12 h-11 text-center border-x border-ink-200 focus:outline-none" min="1" max="99" />
              <button class="w-10 h-11 hover:bg-ink-50 font-bold text-ink-500" @click="qty = Math.min(99, qty + 1)">+</button>
            </div>
          </div>
          <div class="flex-1 flex gap-2 self-end pb-0.5">
            <button class="btn-primary flex-1 !py-3" @click="addToCart(false)">{{ t('product.addCart') }}</button>
            <button class="btn-secondary flex-1 !py-3" @click="addToCart(true)">{{ t('product.buyNow') }}</button>
          </div>
        </div>

        <!-- Tabs -->
        <div class="mt-8">
          <div class="flex border-b border-ink-200">
            <button
              class="px-4 py-2.5 text-sm font-bold -mb-px border-b-2 transition"
              :class="tab === 'description' ? 'border-brand-600 text-brand-700' : 'border-transparent text-ink-400 hover:text-ink-600'"
              @click="tab = 'description'"
            >{{ t('product.description') }}</button>
            <button
              class="px-4 py-2.5 text-sm font-bold -mb-px border-b-2 transition"
              :class="tab === 'shipping' ? 'border-brand-600 text-brand-700' : 'border-transparent text-ink-400 hover:text-ink-600'"
              @click="tab = 'shipping'"
            >{{ t('product.shipping') }}</button>
          </div>
          <div class="py-4 text-sm text-ink-600 leading-relaxed">
            <p v-if="tab === 'description'">{{ desc || '-' }}</p>
            <template v-else>
              <p>{{ t('product.shippingInfo', { amount: money(50000) }) }}</p>
              <p class="mt-2 text-ink-400">{{ t('product.returns') }}</p>
            </template>
          </div>
        </div>
      </div>
    </div>

    <!-- Related -->
    <section v-if="product.related && product.related.length" class="mt-14">
      <SectionTitle :title="t('product.related')" />
      <div class="grid grid-cols-2 md:grid-cols-4 gap-4">
        <ProductCard v-for="p in product.related" :key="p.slug" :product="p" />
      </div>
    </section>
  </div>
</template>
