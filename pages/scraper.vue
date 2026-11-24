<script setup lang="ts">
const { t, tr, srcLabel, locale } = useI18n()
const api = useAdminApi()
const publicBase = useRequestURL().origin
const toast = useToastState()
const money = useMoney()

// ---- showcase: everything this site holds, laid out like the products page ----
const q = ref('')
const category = ref('')
const sort = ref('newest')
const page = ref(1)
const loading = ref(false)
const items = ref<any[]>([])
const total = ref(0)
const pages = ref(1)
const cats = ref<any[]>([])
const loadedOnce = ref(false)

const load = async () => {
  loading.value = true
  try {
    const r = await api<any>('/scraper/listings', {
      params: {
        q: q.value || undefined,
        category: category.value || undefined,
        sort: sort.value,
        lang: locale.value,
        page: page.value,
        per_page: 24
      }
    })
    items.value = r.items || []
    total.value = r.total || 0
    pages.value = r.pages || 1
    loadedOnce.value = true
  } catch (e: any) {
    toast(e?.data?.detail || e?.response?._data?.detail || t('admin.error'))
  } finally {
    loading.value = false
  }
}
load()
api('/scraper/categories').then((r: any) => (cats.value = r || [])).catch(() => {})

// instant search (debounced) - go straight to what you want without pressing Enter
let qTimer: any = null
watch(q, () => {
  clearTimeout(qTimer)
  qTimer = setTimeout(() => { page.value = 1; load() }, 350)
})
watch([category, sort], () => { page.value = 1; load() })
// switching EN/KO re-loads the page so names come back in the new language (missing ones are translated)
watch(locale, () => { item.value = null; load() })

const go = (p: number) => {
  page.value = p
  load()
  if (import.meta.client) window.scrollTo({ top: 0, behavior: 'smooth' })
}

// ---- selection + Shopee package download ----
const item = ref<any>(null)
const previewEl = ref<HTMLElement | null>(null)
const pick = (p: any) => {
  item.value = p.id === item.value?.id ? null : p
  if (item.value && import.meta.client) {
    setTimeout(() => previewEl.value?.scrollIntoView({ behavior: 'smooth', block: 'start' }), 50)
  }
}

const downloading = ref(false)
const download = async () => {
  if (!item.value) return
  downloading.value = true
  try {
    const blob: Blob = await api<Blob>('/scraper/package', {
      method: 'POST',
      body: { product_id: item.value.id, lang: locale.value, public_base: publicBase },
      responseType: 'blob'
    })
    const link = document.createElement('a')
    link.href = URL.createObjectURL(blob)
    link.download = `shopee_listing_${item.value.sku}.zip`
    link.click()
    URL.revokeObjectURL(link.href)
  } catch (e: any) {
    toast(e?.data?.detail || e?.response?._data?.detail || t('admin.error'))
  } finally {
    downloading.value = false
  }
}

// ---- multi-select (kept across pages and searches) ----
const selectedIds = ref<Set<number>>(new Set())
const selCount = computed(() => selectedIds.value.size)
const isSel = (id: number) => selectedIds.value.has(id)
const toggleSel = (id: number) => {
  const s = new Set(selectedIds.value)
  s.has(id) ? s.delete(id) : s.add(id)
  selectedIds.value = s
}
const pageAllSelected = computed(() => items.value.length > 0 && items.value.every((p: any) => isSel(p.id)))
const togglePage = () => {
  const s = new Set(selectedIds.value)
  if (pageAllSelected.value) items.value.forEach((p: any) => s.delete(p.id))
  else items.value.forEach((p: any) => s.add(p.id))
  selectedIds.value = s
}
const selectingAll = ref(false)
const selectAllResults = async () => {
  selectingAll.value = true
  try {
    const r = await api<any>('/scraper/ids', { params: { q: q.value || undefined, category: category.value || undefined } })
    const s = new Set(selectedIds.value)
    ;(r.ids || []).forEach((i: number) => s.add(i))
    selectedIds.value = s
  } catch (e: any) {
    toast(e?.data?.detail || t('admin.error'))
  } finally {
    selectingAll.value = false
  }
}
const clearSel = () => { selectedIds.value = new Set() }

const BATCH = 100
const bulkBusy = ref(false)
const bulkProgress = ref('')
const downloadSelected = async () => {
  const ids = [...selectedIds.value]
  if (!ids.length) return
  bulkBusy.value = true
  const parts = Math.ceil(ids.length / BATCH)
  let skipped = 0
  try {
    for (let i = 0; i < parts; i++) {
      bulkProgress.value = t('scraper.downloadingProgress', { i: i + 1, n: parts })
      const blob: Blob = await api<Blob>('/scraper/package-multi', {
        method: 'POST',
        body: { product_ids: ids.slice(i * BATCH, (i + 1) * BATCH), lang: locale.value, public_base: publicBase },
        responseType: 'blob'
      })
      const link = document.createElement('a')
      link.href = URL.createObjectURL(blob)
      link.download = `shopee_listings_part${i + 1}of${parts}.zip`
      link.click()
      URL.revokeObjectURL(link.href)
      await new Promise((r) => setTimeout(r, 400))
    }
  } catch (e: any) {
    toast(e?.data?.detail || e?.response?._data?.detail || t('admin.error'))
  } finally {
    bulkBusy.value = false
    bulkProgress.value = ''
  }
}

const copy = async (text: string) => {
  if (!text) return
  await navigator.clipboard.writeText(text)
  toast(t('scraper.copied'))
}

// each language shows its own text (translated side is filled automatically; other side only as fallback)
const titleOf = (it: any) => (locale.value === 'ko' ? it.title_ko || it.title_en : it.title_en || it.title_ko) || ''
const descOf = (it: any) => (locale.value === 'ko' ? it.desc_ko || it.desc_en : it.desc_en || it.desc_ko) || ''
const thumbs = (it: any) => (it.images || []).filter((i: string) => typeof i === 'string' && i.trim()).slice(0, 8)

useHead({ title: () => t('scraper.title') })
</script>

<template>
  <div class="max-w-7xl mx-auto px-4 py-8">
    <h1 class="text-3xl font-extrabold text-ink-900 mb-2">{{ t('scraper.title') }}</h1>
    <p class="text-sm text-ink-500 mb-8 max-w-3xl">{{ t('scraper.subtitle') }}</p>

    <div class="flex flex-col md:flex-row gap-8">
      <!-- Sidebar: categories over ALL stored data -->
      <aside class="md:w-56 shrink-0">
        <h3 class="label">{{ t('products.categories') }}</h3>
        <div class="flex md:flex-col gap-1.5 flex-wrap mb-6">
          <button
            class="text-sm text-left px-3 py-2 rounded-lg font-medium transition"
            :class="!category ? 'bg-brand-600 text-white' : 'text-ink-600 hover:bg-ink-100'"
            @click="category = ''"
          >{{ t('products.all') }}</button>
          <button
            v-for="c in cats"
            :key="c.slug"
            class="text-sm text-left px-3 py-2 rounded-lg font-medium transition flex items-center justify-between gap-2"
            :class="category === c.slug ? 'bg-brand-600 text-white' : 'text-ink-600 hover:bg-ink-100'"
            @click="category = c.slug"
          >
            <span>{{ tr(c, 'name') }}</span>
            <span class="text-[10px] opacity-70">{{ c.product_count }}</span>
          </button>
        </div>
      </aside>

      <!-- Main -->
      <div class="flex-1 min-w-0">
        <div class="flex flex-wrap items-center gap-3 mb-5">
          <input
            v-model="q"
            :placeholder="t('scraper.searchPlaceholder')"
            class="input max-w-xs rounded-full"
            type="search"
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

        <p class="text-sm text-ink-400 mb-3">{{ t('scraper.resultsCount', { n: total.toLocaleString() }) }}</p>

        <!-- bulk selection bar -->
        <div class="flex flex-wrap items-center gap-2 mb-4">
          <button class="btn-secondary text-xs !py-2" :disabled="!items.length" @click="togglePage">
            {{ pageAllSelected ? t('scraper.unselectPage') : t('scraper.selectPage') }}
          </button>
          <button class="btn-secondary text-xs !py-2" :disabled="!total || selectingAll" @click="selectAllResults">
            {{ selectingAll ? t('scraper.selectAllLoading') : t('scraper.selectAll', { n: total.toLocaleString() }) }}
          </button>
          <button v-if="selCount" class="btn-ghost text-xs" @click="clearSel">{{ t('scraper.clearSel') }}</button>
          <span v-if="selCount" class="badge bg-brand-600 text-white">{{ t('scraper.selectedN', { n: selCount.toLocaleString() }) }}</span>
          <button v-if="selCount" class="btn-primary text-xs !py-2 ml-auto" :disabled="bulkBusy" @click="downloadSelected">
            {{ bulkBusy ? bulkProgress || '…' : t('scraper.downloadSelected', { n: selCount.toLocaleString() }) }}
          </button>
        </div>

        <!-- selected listing: download panel -->
        <div v-if="item" ref="previewEl" class="card p-5 mb-6">
          <div class="flex flex-wrap items-center gap-2 mb-3">
            <span class="badge bg-ink-100 text-ink-600 font-mono">{{ item.sku }}</span>
            <span v-if="item.source_name" class="badge bg-ink-100 text-ink-500 text-[10px]">{{ srcLabel(item, 'source_name') }}</span>
            <span v-if="item.status !== 'published'" class="badge bg-amber-100 text-amber-700 text-[10px]">{{ t('scraper.statusDraft') }}</span>
            <button class="text-xs text-ink-400 hover:text-brand-700 underline decoration-dotted underline-offset-2 ml-auto" @click="item = null">{{ t('scraper.clear') }}</button>
            <a v-if="item.source_url" :href="item.source_url" target="_blank" rel="noopener" class="text-xs text-ink-400 hover:text-brand-700 underline decoration-dotted underline-offset-2 max-w-[280px] truncate">{{ t('scraper.source') }}</a>
          </div>

          <h2 class="text-lg font-bold text-ink-900 mb-3">{{ titleOf(item) }}</h2>

          <div class="grid sm:grid-cols-3 gap-3 mb-4">
            <div class="card p-3"><div class="text-[11px] uppercase tracking-wider text-ink-400 mb-0.5">{{ t('scraper.priceCost') }}</div><div class="font-extrabold text-ink-900">₩{{ (item.price_cost || 0).toLocaleString() }}</div></div>
            <div class="card p-3"><div class="text-[11px] uppercase tracking-wider text-ink-400 mb-0.5">{{ t('scraper.priceSell') }}</div><div class="font-extrabold text-brand-700">₩{{ (item.price_sell || 0).toLocaleString() }}</div></div>
            <div class="card p-3"><div class="text-[11px] uppercase tracking-wider text-ink-400 mb-0.5">{{ t('scraper.images') }}</div><div class="font-extrabold text-ink-900">{{ item.image_count }}</div></div>
          </div>

          <div class="flex flex-wrap gap-2 mb-5">
            <button class="btn-primary text-sm" :disabled="downloading" @click="download">{{ downloading ? '…' : t('scraper.downloadZip') }}</button>
            <button class="btn-secondary text-sm" @click="copy(titleOf(item))">{{ t('scraper.copyTitle') }}</button>
            <button class="btn-secondary text-sm" @click="copy(descOf(item))">{{ t('scraper.copyDesc') }}</button>
          </div>

          <div v-if="thumbs(item).length" class="flex flex-wrap gap-2 mb-5">
            <img v-for="(im, i) in thumbs(item)" :key="i" :src="im" class="w-24 h-24 object-cover rounded-lg border border-ink-100" loading="lazy" :alt="`image ${i + 1}`" />
          </div>

          <div>
            <div class="text-[11px] uppercase tracking-wider text-ink-400 mb-1">{{ t('scraper.descr') }}</div>
            <p class="text-sm text-ink-600 whitespace-pre-line">{{ descOf(item) || t('scraper.none') }}</p>
          </div>
        </div>

        <!-- product grid (same layout as the products page) -->
        <div v-if="loading && !loadedOnce" class="text-ink-400 py-16 text-center">{{ t('products.loading') }}</div>
        <div v-else-if="loadedOnce && !items.length" class="text-ink-400 py-16 text-center">{{ t('scraper.noResults') }}</div>
        <div v-else class="grid grid-cols-2 md:grid-cols-3 xl:grid-cols-4 gap-4">
          <div v-for="p in items" :key="p.id" class="relative">
          <label
            class="absolute top-2 left-2 z-10 w-7 h-7 rounded-md bg-white/95 border border-ink-200 shadow flex items-center justify-center cursor-pointer"
            :title="t('scraper.pick')"
            @click.stop
          >
            <input type="checkbox" class="w-4 h-4 accent-brand-600 cursor-pointer" :checked="isSel(p.id)" :aria-label="t('scraper.pick')" @change="toggleSel(p.id)" />
          </label>
          <button
            class="card overflow-hidden group flex flex-col text-left hover:shadow-pop transition w-full h-full"
            :class="[item?.id === p.id ? 'ring-2 ring-brand-500' : '', isSel(p.id) ? 'ring-2 ring-brand-400' : '']"
            @click="pick(p)"
          >
            <div class="relative overflow-hidden">
              <div class="aspect-square bg-ink-100">
                <img
                  :src="p.thumb || '/placeholder.svg'"
                  :alt="titleOf(p)"
                  loading="lazy"
                  class="w-full h-full object-cover group-hover:scale-105 transition duration-300"
                />
              </div>
              <span v-if="p.status !== 'published'" class="badge bg-amber-100 text-amber-800 dark:bg-amber-500/15 dark:text-amber-300 absolute top-2 left-11">{{ t('scraper.statusDraft') }}</span>
              <span v-else-if="!p.source_enabled" class="badge bg-ink-100 text-ink-500 absolute top-2 left-11">{{ t('scraper.sourceOff') }}</span>
              <span v-if="item?.id === p.id" class="badge bg-brand-600 text-white absolute top-2 right-2">{{ t('scraper.selected') }}</span>
            </div>
            <div class="p-4 flex flex-col flex-1">
              <div class="text-sm font-semibold text-ink-800 leading-snug line-clamp-2">{{ titleOf(p) }}</div>
              <div class="mt-1.5 flex items-center gap-1 text-xs text-ink-400">
                <span class="font-mono">{{ p.sku }}</span>
                <span>·</span>
                <span>{{ t('scraper.images') }} {{ p.image_count }}</span>
              </div>
              <div class="mt-auto pt-3 flex items-center justify-between gap-2">
                <span class="text-lg font-extrabold text-ink-900">{{ money(p.price_sell) }}</span>
                <span class="btn-primary !px-3 !py-2 text-xs">{{ t('scraper.select') }}</span>
              </div>
            </div>
          </button>
          </div>
        </div>

        <PaginationNav :page="page" :pages="pages" @go="go" />
      </div>
    </div>
  </div>
</template>
