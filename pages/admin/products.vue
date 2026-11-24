<script setup lang="ts">
import type { AdminProduct, AdminCategory } from '~~/types/checkout'

definePageMeta({ layout: 'admin' })
const { t } = useI18n()
const money = useMoney()
const adminApi = useAdminApi()
const toast = useToastState()

const q = ref('')
const status = ref('')
const page = ref(1)

const { data, refresh } = await useAsyncData(
  'admin-products',
  async () =>
    await adminApi<{ items: AdminProduct[]; total: number; pages: number }>('/admin/products', {
      params: { q: q.value || undefined, status: status.value || undefined, page: page.value, per_page: 20 }
    }),
  { watch: [q, status, page] }
)

const { data: cats } = await useAsyncData('admin-cats', async () => await adminApi<AdminCategory[]>('/admin/categories'))

// form state
const showForm = ref(false)
const editing = ref<AdminProduct | null>(null)
const saving = ref(false)
const form = reactive({
  title_ko: '',
  title_en: '',
  desc_ko: '',
  desc_en: '',
  price_cost: 0,
  markup_override: null as number | null,
  images: [] as string[],
  status: 'published',
  category_id: null as number | null,
  stock_status: 'in_stock',
  rating: 4.7,
  reviews: 0
})

const newImageUrl = ref('')
const importing = ref(false)
const uploading = ref(false)
const imgError = ref('')
const fileInput = ref<HTMLInputElement | null>(null)

const importFromUrl = async () => {
  const url = newImageUrl.value.trim()
  if (!url) return
  importing.value = true
  imgError.value = ''
  try {
    const r = await adminApi<{ url: string }>('/admin/fetch-image', { method: 'POST', body: { url } })
    form.images.push(r.url)
    newImageUrl.value = ''
  } catch (e: any) {
    imgError.value = e?.data?.detail || 'Import failed'
  } finally {
    importing.value = false
  }
}

const uploadFile = async () => {
  const f = fileInput.value?.files?.[0]
  if (!f) return
  uploading.value = true
  imgError.value = ''
  try {
    const fd = new FormData()
    fd.append('file', f)
    const r = await adminApi<{ url: string }>('/admin/upload-image', { method: 'POST', body: fd })
    form.images.push(r.url)
    if (fileInput.value) fileInput.value.value = ''
  } catch (e: any) {
    imgError.value = e?.data?.detail || 'Upload failed'
  } finally {
    uploading.value = false
  }
}

const removeImage = (i: number) => {
  form.images.splice(i, 1)
}

const openAdd = () => {
  editing.value = null
  Object.assign(form, { title_ko: '', title_en: '', desc_ko: '', desc_en: '', price_cost: 0, markup_override: null, images: [], status: 'published', category_id: cats.value?.[0]?.id ?? null, stock_status: 'in_stock', rating: 4.7, reviews: 0 })
  newImageUrl.value = ''
  imgError.value = ''
  showForm.value = true
}

const openEdit = (p: AdminProduct) => {
  editing.value = p
  Object.assign(form, {
    title_ko: p.title_ko,
    title_en: p.title_en || '',
    desc_ko: p.desc_ko || '',
    desc_en: p.desc_en || '',
    price_cost: p.price_cost,
    markup_override: p.markup_override,
    images: [...(p.images || [])],
    status: p.status,
    category_id: p.category_id,
    stock_status: p.stock_status,
    rating: p.rating,
    reviews: p.reviews
  })
  newImageUrl.value = ''
  imgError.value = ''
  showForm.value = true
}

const save = async () => {
  saving.value = true
  const body = {
    ...form,
    images: form.images.filter(Boolean)
  }
  try {
    if (editing.value) await adminApi(`/admin/products/${editing.value.id}`, { method: 'PUT', body })
    else await adminApi('/admin/products', { method: 'POST', body })
    showForm.value = false
    toast(t('admin.productForm.saved'))
    refresh()
  } catch (e: any) {
    toast(e?.data?.detail || t('admin.error'))
  } finally {
    saving.value = false
  }
}

const remove = async (p: AdminProduct) => {
  if (!confirm(t('admin.confirmDelete'))) return
  await adminApi(`/admin/products/${p.id}`, { method: 'DELETE' })
  refresh()
}

const retranslate = async (p: AdminProduct) => {
  const r = await adminApi<{ ok: boolean; error?: string }>(`/admin/products/${p.id}/retranslate`, { method: 'POST' })
  toast(r.ok ? 'Translation done' : r.error || 'Translation failed')
  refresh()
}

const reapply = async () => {
  await adminApi('/admin/pricing/reapply', { method: 'POST', body: {} })
  toast(t('admin.saved'))
  refresh()
}

const previewCost = computed(() => {
  const pct = form.markup_override ?? 35
  return money(Math.ceil((form.price_cost || 0) * (1 + pct / 100) / 10) * 10)
})

useHead({ title: () => t('admin.products') })
</script>

<template>
  <div>
    <div class="flex flex-wrap items-center justify-between gap-3 mb-5">
      <h1 class="text-2xl font-extrabold text-ink-900">{{ t('admin.products') }} <span class="text-ink-400 text-lg font-bold">({{ data?.total ?? 0 }})</span></h1>
      <div class="flex gap-2">
        <button class="btn-secondary text-sm" @click="reapply">{{ t('admin.reapplyMarkup') }}</button>
        <button class="btn-primary text-sm" @click="openAdd">+ {{ t('admin.addProduct') }}</button>
      </div>
    </div>

    <div class="flex flex-wrap gap-2 mb-4">
      <input v-model="q" :placeholder="t('admin.searchProducts')" class="input max-w-xs" />
      <select v-model="status" class="input !w-auto">
        <option value="">{{ t('admin.allStatuses') }}</option>
        <option value="published">{{ t('admin.published') }}</option>
        <option value="draft">{{ t('admin.draft') }}</option>
        <option value="archived">{{ t('admin.archived') }}</option>
      </select>
    </div>

    <div class="card overflow-x-auto scroll-thin">
      <table class="w-full text-sm min-w-[860px]">
        <thead>
          <tr class="text-left text-xs uppercase tracking-wider text-ink-400 border-b border-ink-100">
            <th class="px-4 py-3">{{ t('admin.title') }}</th>
            <th class="px-3 py-3">{{ t('admin.cost') }}</th>
            <th class="px-3 py-3">{{ t('admin.sell') }}</th>
            <th class="px-3 py-3">{{ t('admin.margin') }}</th>
            <th class="px-3 py-3">{{ t('admin.status') }}</th>
            <th class="px-3 py-3">{{ t('admin.source') }}</th>
            <th class="px-3 py-3 text-right">{{ t('admin.actions') }}</th>
          </tr>
        </thead>
        <tbody class="divide-y divide-ink-50">
          <tr v-for="p in data?.items || []" :key="p.id" class="hover:bg-ink-50/50">
            <td class="px-4 py-3">
              <div class="flex items-center gap-3">
                <div class="w-11 h-11 rounded-lg overflow-hidden bg-ink-100 shrink-0">
                  <SmartImage :src="p.images?.[0] || null" :alt="p.title_en || p.title_ko" />
                </div>
                <div class="min-w-0">
                  <div class="font-semibold text-ink-800 line-clamp-1 max-w-xs">{{ p.title_en || p.title_ko }}</div>
                  <div class="text-xs text-ink-400 line-clamp-1 max-w-xs">{{ p.title_ko }}</div>
                </div>
              </div>
            </td>
            <td class="px-3 py-3 text-ink-600">{{ money(p.price_cost) }}</td>
            <td class="px-3 py-3 font-bold text-ink-900">{{ money(p.price_sell) }}</td>
            <td class="px-3 py-3">
              <span class="badge bg-emerald-50 text-emerald-700">{{ p.effective_margin_pct }}%</span>
            </td>
            <td class="px-3 py-3">
              <span class="badge" :class="p.status === 'published' ? 'bg-brand-100 text-brand-800' : p.status === 'archived' ? 'bg-amber-100 text-amber-800' : 'bg-ink-100 text-ink-500'">{{ p.status === 'published' ? t('admin.published') : p.status === 'archived' ? t('admin.archived') : t('admin.draft') }}</span>
              <span v-if="p.translation_status === 'pending'" class="badge bg-amber-100 text-amber-700 ml-1">KO</span>
            </td>
            <td class="px-3 py-3 text-ink-500 text-xs max-w-[130px] truncate">{{ p.source_name || (p.is_manual ? 'Manual' : '-') }}</td>
            <td class="px-3 py-3">
              <div class="flex justify-end gap-1">
                <button class="btn-ghost text-xs" @click="openEdit(p)">{{ t('admin.edit') }}</button>
                <button v-if="p.translation_status !== 'done'" class="btn-ghost text-xs text-amber-600" @click="retranslate(p)">{{ t('admin.retranslate') }}</button>
                <button class="btn-ghost text-xs text-rose-600" @click="remove(p)">{{ t('admin.delete') }}</button>
              </div>
            </td>
          </tr>
        </tbody>
      </table>
    </div>

    <PaginationNav v-if="data" :page="data.page" :pages="data.pages" @go="(p) => (page = p)" />

    <AdminModal :open="showForm" :title="editing ? t('admin.edit') : t('admin.addProduct')" wide @close="showForm = false">
      <form class="grid md:grid-cols-2 gap-4" @submit.prevent="save">
        <div><span class="label">{{ t('admin.productForm.titleKo') }}</span><input v-model="form.title_ko" class="input" /></div>
        <div><span class="label">{{ t('admin.productForm.titleEn') }}</span><input v-model="form.title_en" class="input" /></div>
        <div><span class="label">{{ t('admin.productForm.descKo') }}</span><textarea v-model="form.desc_ko" rows="3" class="input" /></div>
        <div><span class="label">{{ t('admin.productForm.descEn') }}</span><textarea v-model="form.desc_en" rows="3" class="input" /></div>
        <div>
          <span class="label">{{ t('admin.productForm.priceCost') }}</span>
          <input v-model.number="form.price_cost" type="number" min="0" class="input" />
        </div>
        <div>
          <span class="label">{{ t('admin.productForm.markupOverride') }}</span>
          <input v-model.number="form.markup_override" type="number" step="0.1" min="0" class="input" placeholder="35" />
          <p class="text-xs text-ink-400 mt-1">{{ t('admin.sell') }}: <b>{{ previewCost }}</b></p>
        </div>
        <div class="md:col-span-2">
          <span class="label">{{ t('admin.productForm.images') }}</span>
          <div class="flex flex-wrap items-center gap-2 mb-2">
            <input
              v-model="newImageUrl"
              class="input !w-auto flex-1 min-w-[220px] text-xs"
              :placeholder="t('admin.productForm.imageUrlHint')"
              @keyup.enter="importFromUrl"
            />
            <button type="button" class="btn-secondary text-xs" :disabled="importing || !newImageUrl.trim()" @click="importFromUrl">{{ importing ? '...' : t('admin.productForm.import') }}</button>
            <button type="button" class="btn-secondary text-xs" :disabled="uploading" @click="fileInput?.click()">{{ uploading ? '...' : t('admin.productForm.upload') }}</button>
            <input ref="fileInput" type="file" accept="image/*" class="hidden" @change="uploadFile" />
          </div>
          <p v-if="imgError" class="text-xs text-rose-600 mb-2">{{ imgError }}</p>
          <div v-if="form.images.length" class="flex flex-wrap gap-2">
            <div v-for="(img, i) in form.images" :key="img + i" class="relative w-16 h-16 rounded-lg overflow-hidden border border-ink-200 bg-ink-50 group">
              <SmartImage :src="img" alt="Product image" eager />
              <button
                type="button"
                class="absolute top-0 right-0 w-5 h-5 bg-rose-600 text-white text-[10px] font-bold flex items-center justify-center"
                :aria-label="t('cart.remove')"
                @click="removeImage(i)"
              >×</button>
            </div>
          </div>
          <p v-else class="text-xs text-ink-400">{{ t('admin.productForm.imagesEmpty') }}</p>
        </div>
        <div>
          <span class="label">{{ t('admin.productForm.category') }}</span>
          <select v-model.number="form.category_id" class="input">
            <option :value="null">-</option>
            <option v-for="c in cats || []" :key="c.id" :value="c.id">{{ c.name_en }}</option>
          </select>
        </div>
        <div>
          <span class="label">{{ t('admin.status') }}</span>
          <select v-model="form.status" class="input">
            <option value="published">{{ t('admin.published') }}</option>
            <option value="draft">{{ t('admin.draft') }}</option>
            <option value="archived">{{ t('admin.archived') }}</option>
          </select>
        </div>
        <div class="md:col-span-2 text-right">
          <button class="btn-primary" :disabled="saving">{{ saving ? '…' : t('admin.productForm.save') }}</button>
        </div>
      </form>
    </AdminModal>
  </div>
</template>
