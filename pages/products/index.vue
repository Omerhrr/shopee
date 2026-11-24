<script setup lang="ts">
const api = useApi()
const { t, tr } = useI18n()
const route = useRoute()
const router = useRouter()

const q = ref((route.query.q as string) || '')
const category = ref((route.query.category as string) || '')
const sort = ref((route.query.sort as string) || 'newest')
const page = ref(Number(route.query.page) || 1)

const { data, pending } = await useAsyncData(
  'products-list',
  async () =>
    await api('/catalog/products', {
      params: {
        q: q.value || undefined,
        category: category.value || undefined,
        sort: sort.value,
        page: page.value,
        per_page: 24
      }
    }),
  { watch: [q, category, sort, page] }
)

const { data: cats } = await useAsyncData('cats-sidebar', async () => await api('/catalog/categories'))

watch([q, category, sort, page], () => {
  router.replace({ query: { q: q.value || undefined, category: category.value || undefined, sort: sort.value === 'newest' ? undefined : sort.value, page: page.value > 1 ? page.value : undefined } })
})

watch(() => route.query, (nq) => {
  q.value = (nq.q as string) || ''
  category.value = (nq.category as string) || ''
  sort.value = (nq.sort as string) || 'newest'
  page.value = Number(nq.page) || 1
})

const go = (p: number) => {
  page.value = p
  if (import.meta.client) window.scrollTo({ top: 0, behavior: 'smooth' })
}

useHead({ title: () => t('products.title') })
</script>

<template>
  <div class="max-w-7xl mx-auto px-4 py-8">
    <div class="flex flex-col md:flex-row gap-8">
      <!-- Sidebar -->
      <aside class="md:w-56 shrink-0">
        <h3 class="label">{{ t('products.categories') }}</h3>
        <div class="flex md:flex-col gap-1.5 flex-wrap mb-6">
          <button
            class="text-sm text-left px-3 py-2 rounded-lg font-medium transition"
            :class="!category ? 'bg-brand-600 text-white' : 'text-ink-600 hover:bg-ink-100'"
            @click="category = ''"
          >{{ t('products.all') }}</button>
          <button
            v-for="c in cats || []"
            :key="c.slug"
            class="text-sm text-left px-3 py-2 rounded-lg font-medium transition"
            :class="category === c.slug ? 'bg-brand-600 text-white' : 'text-ink-600 hover:bg-ink-100'"
            @click="category = c.slug"
          >{{ tr(c, 'name') }}</button>
        </div>
      </aside>

      <!-- Main -->
      <div class="flex-1 min-w-0">
        <div class="flex flex-wrap items-center gap-3 mb-5">
          <input
            v-model="q"
            :placeholder="t('nav.searchPlaceholder')"
            class="input max-w-xs rounded-full"
            type="search"
            @keyup.enter="go(1)"
          />
          <div class="ml-auto flex items-center gap-2">
            <span class="text-xs font-semibold text-ink-400 uppercase tracking-wide">{{ t('products.sort') }}</span>
            <select v-model="sort" class="input !w-auto !py-2 rounded-lg text-sm">
              <option value="newest">{{ t('products.sortNewest') }}</option>
              <option value="popular">{{ t('products.sortPopular') }}</option>
              <option value="price_asc">{{ t('products.sortPriceAsc') }}</option>
              <option value="price_desc">{{ t('products.sortPriceDesc') }}</option>
            </select>
          </div>
        </div>

        <p class="text-sm text-ink-400 mb-4">{{ data ? t('products.resultsFor', { n: data.total }) : '' }}</p>

        <div v-if="pending && !data" class="text-ink-400 py-16 text-center">{{ t('products.loading') }}</div>
        <div v-else-if="!data || !data.items.length" class="text-ink-400 py-16 text-center">{{ t('products.noResults') }}</div>
        <div v-else class="grid grid-cols-2 md:grid-cols-3 xl:grid-cols-4 gap-4">
          <ProductCard v-for="p in data.items" :key="p.slug" :product="p" />
        </div>

        <PaginationNav v-if="data" :page="data.page" :pages="data.pages" @go="go" />
      </div>
    </div>
  </div>
</template>
