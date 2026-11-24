<script setup lang="ts">
import type { AdminSource, AdminCategory } from '~~/types/checkout'

definePageMeta({ layout: 'admin' })
const { t, locale } = useI18n()
const adminApi = useAdminApi()
const toast = useToastState()

const q = ref('')
const filterEnabled = ref('')

const { data: sources, refresh } = await useAsyncData(
  'admin-sources',
  async () =>
    await adminApi<AdminSource[]>('/admin/sources', {
      params: { q: q.value || undefined, enabled: filterEnabled.value || undefined }
    }),
  { watch: [q, filterEnabled] }
)
const { data: cats } = await useAsyncData('admin-cats', async () => await adminApi<AdminCategory[]>('/admin/categories'))

const toggle = async (s: AdminSource) => {
  await adminApi(`/admin/sources/${s.id}`, {
    method: 'PUT',
    body: { name: s.name, url: s.url, adapter: s.adapter, config: s.config, enabled: !s.enabled, notes: s.notes, contact: s.contact }
  })
  refresh()
}

const remove = async (s: AdminSource) => {
  if (!confirm(t('admin.confirmDelete'))) return
  await adminApi(`/admin/sources/${s.id}`, { method: 'DELETE' })
  refresh()
}

// edit modal
const showForm = ref(false)
const editing = ref<AdminSource | null>(null)
const form = reactive({ name: '', url: '', listing_url: '', max_products: 2000, max_pages: 20, category_id: null as number | null, contact: '', notes: '', enabled: false })

const openEdit = (s: AdminSource) => {
  editing.value = s
  Object.assign(form, {
    name: s.name,
    url: s.url,
    listing_url: s.config?.listing_url || '',
    max_products: s.config?.max_products || 2000,
    max_pages: s.config?.max_pages || 20,
    category_id: s.config?.category_id ?? null,
    contact: s.contact,
    notes: s.notes,
    enabled: s.enabled
  })
  showForm.value = true
}

const save = async () => {
  const body = {
    name: form.name,
    url: form.url,
    adapter: 'generic',
    config: { listing_url: form.listing_url || undefined, max_products: form.max_products, max_pages: form.max_pages, category_id: form.category_id },
    enabled: form.enabled,
    notes: form.notes,
    contact: form.contact
  }
  if (editing.value) await adminApi(`/admin/sources/${editing.value.id}`, { method: 'PUT', body })
  else await adminApi('/admin/sources', { method: 'POST', body })
  showForm.value = false
  toast(t('admin.saved'))
  refresh()
}

// test modal
const testResult = ref<null | { ok: boolean; found_links?: number; samples?: any[]; error?: string }>(null)
const testTarget = ref('')
const testing = ref(false)
const runTest = async (s: AdminSource) => {
  testTarget.value = s.name
  testing.value = true
  testResult.value = null
  testResult.value = await adminApi(`/admin/sources/${s.id}/test`, { method: 'POST' })
  testing.value = false
}

// scrape now
const scrapingId = ref(0)
const scrapeNow = async (s: AdminSource) => {
  scrapingId.value = s.id
  try {
    const r = await adminApi(`/admin/sources/${s.id}/scrape`, { method: 'POST' })
    toast(`${s.name}: ${r.status} · +${r.new} new, ${r.updated} updated`)
    refresh()
    refreshNuxtData('admin-scrape-logs')
  } catch {
    toast(t('admin.error'))
  } finally {
    scrapingId.value = 0
  }
}

const statusBadge = (s: AdminSource) =>
  s.status === 'ok' ? 'bg-emerald-50 text-emerald-700 dark:bg-emerald-500/15 dark:text-emerald-300' : s.status === 'error' ? 'bg-rose-50 text-rose-700 dark:bg-rose-500/15 dark:text-rose-300' : 'bg-ink-100 text-ink-500'

useHead({ title: () => t('admin.sources') })
</script>

<template>
  <div>
    <h1 class="text-2xl font-extrabold text-ink-900 mb-2">{{ t('admin.sources') }}</h1>
    <p class="text-sm text-ink-500 mb-5 max-w-3xl">{{ t('admin.sourcesHint') }}</p>

    <div class="flex flex-wrap gap-2 mb-4">
      <input v-model="q" :placeholder="`${t('admin.name')} / ${t('admin.url')}`" class="input max-w-xs" />
      <select v-model="filterEnabled" class="input !w-auto">
        <option value="">{{ t('products.all') }}</option>
        <option value="true">{{ t('admin.enabled') }} ✓</option>
        <option value="false">{{ t('admin.enabled') }} ✕</option>
      </select>
      <span class="ml-auto text-sm text-ink-400 self-center">{{ sources?.length ?? 0 }}</span>
    </div>

    <div class="card overflow-x-auto scroll-thin">
      <table class="w-full text-sm min-w-[900px]">
        <thead>
          <tr class="text-left text-xs uppercase tracking-wider text-ink-400 border-b border-ink-100">
            <th class="px-4 py-3">{{ t('admin.name') }}</th>
            <th class="px-3 py-3">{{ t('admin.url') }}</th>
            <th class="px-3 py-3">{{ t('admin.categoryHint') }}</th>
            <th class="px-3 py-3">{{ t('admin.flags') }}</th>
            <th class="px-3 py-3">{{ t('admin.enabled') }}</th>
            <th class="px-3 py-3">{{ t('admin.lastScraped') }}</th>
            <th class="px-3 py-3 text-right">{{ t('admin.actions') }}</th>
          </tr>
        </thead>
        <tbody class="divide-y divide-ink-50">
          <tr v-for="s in sources || []" :key="s.id" class="hover:bg-ink-50/50">
            <td class="px-4 py-3">
              <div class="font-semibold text-ink-800">{{ s.name }}</div>
              <div class="text-xs text-ink-400">{{ t('admin.productCount', { n: s.product_count }) }}</div>
            </td>
            <td class="px-3 py-3">
              <a v-if="s.url" :href="s.url" target="_blank" rel="noopener" class="text-xs text-ink-500 hover:text-brand-700 max-w-[180px] truncate block">{{ s.url }}</a>
              <span v-else class="text-xs text-ink-300">-</span>
            </td>
            <td class="px-3 py-3 text-xs text-ink-500 max-w-[140px] truncate">{{ s.category_hint }}</td>
            <td class="px-3 py-3">
              <div class="flex flex-wrap gap-1">
                <span v-if="s.paid_membership" class="badge bg-amber-100 text-amber-800 dark:bg-amber-500/15 dark:text-amber-300 text-[10px]">{{ t('admin.paid') }}</span>
                <span v-if="s.requires_cafe" class="badge bg-ink-100 text-ink-600 text-[10px]">{{ t('admin.cafe') }}</span>
                <span v-if="!s.image_provided" class="badge bg-ink-100 text-ink-600 text-[10px]">{{ t('admin.noImg') }}</span>
              </div>
            </td>
            <td class="px-3 py-3">
              <button
                class="w-11 h-6 rounded-full relative transition"
                :class="s.enabled ? 'bg-brand-600' : 'bg-ink-200'"
                :aria-label="t('admin.enabled')"
                :title="s.enabled ? t('admin.disableHides') : t('admin.enableRestores')"
                @click="toggle(s)"
              >
                <span class="absolute top-0.5 w-5 h-5 rounded-full bg-white shadow transition-all" :class="s.enabled ? 'left-[22px]' : 'left-0.5'" />
              </button>
            </td>
            <td class="px-3 py-3">
              <span
                class="badge text-[10px]"
                :class="[statusBadge(s), s.status === 'error' && s.last_error ? 'cursor-help underline decoration-dotted underline-offset-2' : '']"
                :title="s.last_error || s.status"
              >{{ s.status }}</span>
              <div class="text-[11px] text-ink-400 mt-0.5">{{ s.last_scraped_at ? new Date(s.last_scraped_at).toLocaleString() : '-' }}</div>
            </td>
            <td class="px-3 py-3">
              <div class="flex justify-end gap-1 whitespace-nowrap">
                <button class="btn-ghost text-xs" @click="runTest(s)">{{ testing && testTarget === s.name ? '…' : t('admin.test') }}</button>
                <button class="btn-ghost text-xs text-brand-700" :disabled="scrapingId === s.id || !s.enabled" @click="scrapeNow(s)">{{ scrapingId === s.id ? '…' : t('admin.scrapeNow') }}</button>
                <button class="btn-ghost text-xs" @click="openEdit(s)">{{ t('admin.edit') }}</button>
                <button class="btn-ghost text-xs text-rose-600" @click="remove(s)">{{ t('admin.delete') }}</button>
              </div>
            </td>
          </tr>
        </tbody>
      </table>
    </div>

    <AdminModal :open="showForm" :title="t('admin.editSource')" wide @close="showForm = false">
      <form class="grid md:grid-cols-2 gap-4" @submit.prevent="save">
        <div><span class="label">{{ t('admin.name') }}</span><input v-model="form.name" class="input" required /></div>
        <div><span class="label">{{ t('admin.url') }}</span><input v-model="form.url" class="input" /></div>
        <div class="md:col-span-2"><span class="label">{{ t('admin.sourceForm.listingUrl') }}</span><input v-model="form.listing_url" class="input" placeholder="https://…/shop/goods/goods_list.php" /></div>
        <div>
          <span class="label">{{ t('admin.sourceForm.maxProducts') }}</span>
          <input v-model.number="form.max_products" type="number" min="1" max="5000" class="input" />
        </div>
        <div>
          <span class="label">{{ t('admin.sourceForm.maxPages') }}</span>
          <input v-model.number="form.max_pages" type="number" min="1" max="30" class="input" />
        </div>
        <div>
          <span class="label">{{ t('admin.sourceForm.mapCategory') }}</span>
          <select v-model.number="form.category_id" class="input">
            <option :value="null">-</option>
            <option v-for="c in cats || []" :key="c.id" :value="c.id">{{ locale === 'ko' ? c.name_ko : c.name_en }}</option>
          </select>
        </div>
        <div><span class="label">{{ t('admin.sourceForm.contact') }}</span><input v-model="form.contact" class="input" /></div>
        <div class="flex items-end gap-3">
          <label class="flex items-center gap-2 text-sm font-semibold text-ink-700">
            <input v-model="form.enabled" type="checkbox" class="w-4 h-4 accent-brand-600" />
            {{ t('admin.enabled') }}
          </label>
        </div>
        <div class="md:col-span-2"><span class="label">{{ t('admin.sourceForm.notes') }}</span><textarea v-model="form.notes" rows="2" class="input" /></div>
        <div class="md:col-span-2 text-right">
          <button class="btn-primary" :disabled="form.enabled && !form.url">{{ t('admin.save') }}</button>
        </div>
      </form>
    </AdminModal>

    <AdminModal :open="!!testResult" :title="`${t('admin.test')} - ${testTarget}`" @close="testResult = null">
      <div v-if="testResult">
        <p v-if="!testResult.ok" class="text-sm text-rose-600 font-semibold">{{ testResult.error }}</p>
        <template v-else>
          <p class="text-sm text-ink-600">{{ t('admin.testResults', { n: testResult.found_links || 0 }) }}</p>
          <div class="mt-3 space-y-2">
            <div v-for="(s, i) in testResult.samples || []" :key="i" class="card p-3 text-sm">
              <div class="font-semibold text-ink-800">{{ s.title || '(no title)' }}</div>
              <div class="text-xs text-ink-400 mt-0.5">₩ {{ s.price ?? '?' }} · {{ s.url }}</div>
            </div>
          </div>
        </template>
      </div>
    </AdminModal>
  </div>
</template>
