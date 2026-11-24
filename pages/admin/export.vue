<script setup lang="ts">
import type { AdminSource, AdminCategory } from '~~/types/checkout'

definePageMeta({ layout: 'admin' })
const { t, locale } = useI18n()
const adminApi = useAdminApi()
const toast = useToastState()

// filters (shared by preview + downloads)
const q = ref('')
const categoryId = ref<number | null>(null)
const sourceId = ref<number | null>(null)
// export options
const titleLang = ref('en')
const currency = ref('KRW')
const usdRate = ref(1350)
const stock = ref(10)
const weightG = ref(500)
const lengthCm = ref(25)
const widthCm = ref(20)
const heightCm = ref(10)
const publicBase = ref('http://localhost:3000')

const qp = () => {
  const p: any = {
    q: q.value || undefined,
    category_id: categoryId.value ?? undefined,
    source_id: sourceId.value ?? undefined,
    title_lang: titleLang.value,
    currency: currency.value,
    usd_rate: currency.value === 'USD' ? usdRate.value : undefined,
    stock: stock.value,
    weight_g: weightG.value,
    length_cm: lengthCm.value,
    width_cm: widthCm.value,
    height_cm: heightCm.value,
    public_base: publicBase.value
  }
  Object.keys(p).forEach((k) => p[k] === undefined && delete p[k])
  return p
}

const { data: sources } = await useAsyncData('admin-sources-export', async () => await adminApi<AdminSource[]>('/admin/sources'))
const { data: cats } = await useAsyncData('admin-cats-export', async () => await adminApi<AdminCategory[]>('/admin/categories'))

const { data: preview, pending, refresh } = await useAsyncData(
  'admin-export-preview',
  async () => await adminApi<any>('/admin/export/shopee/preview', { params: qp() }),
  { watch: [q, categoryId, sourceId] }
)

const busy = ref('')
const download = async (kind: 'csv' | 'zip') => {
  busy.value = kind
  try {
    const blob: Blob = await adminApi<Blob>(`/admin/export/shopee${kind === 'csv' ? '.csv' : '-images.zip'}`, {
      params: qp(),
      responseType: 'blob'
    })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = kind === 'csv' ? 'shopee_mass_upload.csv' : 'shopee_images.zip'
    a.click()
    URL.revokeObjectURL(url)
  } catch {
    toast(t('admin.error'))
  } finally {
    busy.value = ''
  }
}

const catName = (c: any) => (locale.value === 'ko' ? c.name_ko || c.name_en : c.name_en)
useHead({ title: () => t('admin.export') })
</script>

<template>
  <div>
    <h1 class="text-2xl font-extrabold text-ink-900 mb-2">{{ t('admin.export') }}</h1>
    <p class="text-sm text-ink-500 mb-5 max-w-3xl">{{ t('admin.exportHint') }}</p>

    <!-- Two routes -->
    <div class="grid md:grid-cols-2 gap-4 mb-6">
      <div class="card p-4 border-l-4 border-l-brand-600">
        <div class="flex items-center gap-2 mb-2">
          <span class="badge bg-brand-50 text-brand-700 dark:bg-brand-500/15 dark:text-brand-300 text-[10px]">{{ t('admin.exportRouteNow') }}</span>
          <h2 class="font-bold text-ink-800">{{ t('admin.exportCsvTitle') }}</h2>
        </div>
        <ol class="text-sm text-ink-600 space-y-1.5 list-decimal list-inside">
          <li>{{ t('admin.exportCsvStep1') }}</li>
          <li>{{ t('admin.exportCsvStep2') }}</li>
          <li>{{ t('admin.exportCsvStep3') }}</li>
          <li>{{ t('admin.exportCsvStep4') }}</li>
        </ol>
      </div>
      <div class="card p-4 border-l-4 border-l-ink-200">
        <div class="flex items-center gap-2 mb-2">
          <span class="badge bg-ink-100 text-ink-600 text-[10px]">{{ t('admin.exportRouteApi') }}</span>
          <h2 class="font-bold text-ink-800">{{ t('admin.exportApiTitle') }}</h2>
        </div>
        <ol class="text-sm text-ink-600 space-y-1.5 list-decimal list-inside">
          <li>{{ t('admin.exportApiStep1') }}</li>
          <li>{{ t('admin.exportApiStep2') }}</li>
          <li>{{ t('admin.exportApiStep3') }}</li>
          <li>{{ t('admin.exportApiStep4') }}</li>
        </ol>
      </div>
    </div>

    <!-- Export settings -->
    <div class="card p-4 mb-6">
      <h2 class="font-bold text-ink-800 mb-3">{{ t('admin.exportSettings') }}</h2>
      <div class="grid sm:grid-cols-2 lg:grid-cols-4 gap-3">
        <div><span class="label">{{ t('admin.searchProducts') }}</span><input v-model="q" class="input" :placeholder="t('admin.searchProducts')" /></div>
        <div>
          <span class="label">{{ t('admin.source') }}</span>
          <select v-model.number="sourceId" class="input">
            <option :value="null">{{ t('products.all') }}</option>
            <option v-for="s in sources || []" :key="s.id" :value="s.id">{{ s.name }} ({{ s.product_count }})</option>
          </select>
        </div>
        <div>
          <span class="label">{{ t('admin.productForm.category') }}</span>
          <select v-model.number="categoryId" class="input">
            <option :value="null">{{ t('products.all') }}</option>
            <option v-for="c in cats || []" :key="c.id" :value="c.id">{{ catName(c) }}</option>
          </select>
        </div>
        <div>
          <span class="label">{{ t('admin.exportTitleLang') }}</span>
          <select v-model="titleLang" class="input">
            <option value="en">English → 한국어 fallback</option>
            <option value="ko">한국어 → English fallback</option>
          </select>
        </div>
        <div>
          <span class="label">{{ t('admin.exportCurrency') }}</span>
          <select v-model="currency" class="input">
            <option value="KRW">KRW (₩)</option>
            <option value="USD">USD ($)</option>
          </select>
        </div>
        <div v-if="currency === 'USD'">
          <span class="label">{{ t('admin.exportFxRate') }}</span>
          <input v-model.number="usdRate" type="number" min="100" max="5000" step="1" class="input" />
        </div>
        <div><span class="label">{{ t('admin.exportStock') }}</span><input v-model.number="stock" type="number" min="1" class="input" /></div>
        <div><span class="label">{{ t('admin.exportWeight') }}</span><input v-model.number="weightG" type="number" min="50" class="input" /></div>
        <div><span class="label">{{ t('admin.exportDims') }}</span>
          <div class="flex gap-2">
            <input v-model.number="lengthCm" type="number" min="1" class="input" aria-label="L" />
            <input v-model.number="widthCm" type="number" min="1" class="input" aria-label="W" />
            <input v-model.number="heightCm" type="number" min="1" class="input" aria-label="H" />
          </div>
        </div>
        <div class="sm:col-span-2"><span class="label">{{ t('admin.exportPublicUrl') }}</span><input v-model="publicBase" class="input" placeholder="https://your-store.com" /></div>
      </div>
      <p class="text-xs text-ink-400 mt-2">{{ t('admin.exportPublicHint') }}</p>
    </div>

    <!-- Stats + downloads -->
    <div class="card p-4 mb-6">
      <div class="flex flex-wrap items-center gap-3 mb-4">
        <div class="text-sm font-semibold text-ink-700">{{ t('admin.exportReady', { n: preview?.exportable ?? '…' }) }}</div>
        <span class="badge bg-ink-100 text-ink-600 text-[11px]">{{ t('admin.exportTotal', { n: preview?.total ?? 0 }) }}</span>
        <span class="badge bg-amber-50 text-amber-700 dark:bg-amber-500/15 dark:text-amber-300 text-[11px]">{{ t('admin.exportNeedTranslation', { n: preview?.needs_translation ?? 0 }) }}</span>
        <span class="badge bg-rose-50 text-rose-700 dark:bg-rose-500/15 dark:text-rose-300 text-[11px]">{{ t('admin.exportNoImage', { n: preview?.no_image ?? 0 }) }}</span>
        <button class="btn-ghost text-xs ml-auto" :disabled="pending" @click="refresh">{{ pending ? '…' : t('admin.exportRefresh') }}</button>
      </div>
      <div class="flex flex-wrap gap-3">
        <button class="btn-primary text-sm" :disabled="busy !== '' || !preview?.exportable" @click="download('csv')">
          {{ busy === 'csv' ? '…' : t('admin.exportCsvBtn') }}
        </button>
        <button class="btn-secondary text-sm" :disabled="busy !== '' || !preview?.exportable" @click="download('zip')">
          {{ busy === 'zip' ? '…' : t('admin.exportZipBtn') }}
        </button>
      </div>
      <p class="text-xs text-ink-400 mt-2">{{ t('admin.exportCategoryNote') }}</p>
    </div>

    <!-- Preview -->
    <div class="card overflow-x-auto scroll-thin mb-6">
      <table class="w-full text-sm min-w-[700px]">
        <thead>
          <tr class="text-left text-xs uppercase tracking-wider text-ink-400 border-b border-ink-100">
            <th class="px-4 py-3">SKU</th>
            <th class="px-3 py-3">{{ t('admin.title') }}</th>
            <th class="px-3 py-3">{{ t('admin.exportPriceCol', { c: currency }) }}</th>
            <th class="px-3 py-3">{{ t('admin.productForm.category') }}</th>
            <th class="px-3 py-3 text-right">{{ t('admin.exportImagesCol') }}</th>
          </tr>
        </thead>
        <tbody class="divide-y divide-ink-50">
          <tr v-for="r in preview?.samples || []" :key="r.sku" class="hover:bg-ink-50/50">
            <td class="px-4 py-3 font-mono text-xs text-ink-500">{{ r.sku }}</td>
            <td class="px-3 py-3 text-ink-800 max-w-[420px] truncate">{{ r.title }}</td>
            <td class="px-3 py-3 text-ink-800">{{ r.price }}</td>
            <td class="px-3 py-3 text-xs text-ink-500">{{ locale === 'ko' ? r.category_ko : r.category_en }}</td>
            <td class="px-3 py-3 text-right text-xs text-ink-500">{{ r.images }}</td>
          </tr>
          <tr v-if="!preview?.samples?.length">
            <td colspan="5" class="px-4 py-6 text-center text-sm text-ink-400">{{ t('admin.exportEmpty') }}</td>
          </tr>
        </tbody>
      </table>
    </div>

    <!-- Compliance note -->
    <div class="card p-4 bg-amber-50/60 dark:bg-amber-500/10 border border-amber-200 dark:border-amber-500/20">
      <p class="text-sm text-amber-800 dark:text-amber-200"><b>{{ t('admin.exportComplianceTitle') }}</b> {{ t('admin.exportCompliance') }}</p>
    </div>
  </div>
</template>
