<script setup lang="ts">
import type { AdminCategory } from '~~/types/checkout'

definePageMeta({ layout: 'admin' })
const { t } = useI18n()
const money = useMoney()
const adminApi = useAdminApi()
const toast = useToastState()

const days = ref(30)
const { data, refresh } = await useAsyncData(
  'admin-finance',
  async () => await adminApi<any>('/admin/finance/summary', { params: { days: days.value } }),
  { watch: [days] }
)

// markup rules
const { data: cats, refresh: refreshCats } = await useAsyncData('admin-cats-fin', async () => await adminApi<AdminCategory[]>('/admin/categories'))
const globalMarkup = ref(35)
const settingsData = await useAsyncData('admin-settings-fin', async () => await adminApi<Record<string, any>>('/admin/settings'))
globalMarkup.value = Number(settingsData.data.value?.markup_percent ?? 35)

const catMarkups = reactive<Record<number, string>>({})
watchEffect(() => {
  for (const c of cats.value || []) {
    catMarkups[c.id] = c.markup_percent != null ? String(c.markup_percent) : ''
  }
})

const savePricing = async () => {
  for (const c of cats.value || []) {
    const raw = catMarkups[c.id]
    const val = raw === '' ? null : Number(raw)
    if (val !== c.markup_percent && (val === null || (!isNaN(val) && val >= 0))) {
      await adminApi(`/admin/categories/${c.id}`, {
        method: 'PUT',
        body: { slug: c.slug, name_en: c.name_en, name_ko: c.name_ko, markup_percent: val, sort_order: c.sort_order }
      })
    }
  }
  await adminApi('/admin/settings', { method: 'PUT', body: { markup_percent: globalMarkup.value } })
  await adminApi('/admin/pricing/reapply', { method: 'POST', body: {} })
  toast(t('admin.saved'))
  refreshCats()
  refresh()
}

const maxDaily = computed(() => Math.max(1, ...(data.value?.daily || []).map((d: any) => d.revenue)))

useHead({ title: () => t('admin.finance') })
</script>

<template>
  <div>
    <div class="flex items-center justify-between mb-6">
      <h1 class="text-2xl font-extrabold text-ink-900">{{ t('admin.finance') }}</h1>
      <select v-model.number="days" class="input !w-auto">
        <option :value="7">7d</option>
        <option :value="30">30d</option>
        <option :value="90">90d</option>
      </select>
    </div>

    <div class="grid grid-cols-2 lg:grid-cols-6 gap-3 mb-6">
      <StatCard :label="t('admin.revenue')" :value="money(data?.revenue)" accent="brand" />
      <StatCard :label="t('admin.finCost')" :value="money(data?.cost)" />
      <StatCard :label="t('admin.profit')" :value="money(data?.profit)" accent="green" />
      <StatCard :label="t('admin.finMargin')" :value="`${data?.margin_pct ?? 0}%`" />
      <StatCard :label="t('admin.ordersN')" :value="String(data?.orders ?? 0)" />
      <StatCard :label="t('admin.aov')" :value="money(data?.aov)" />
    </div>

    <div class="card p-6 mb-6">
      <h3 class="font-extrabold text-ink-900 mb-4">{{ t('admin.lastDays', { n: days }) }}</h3>
      <div v-if="!data?.daily?.length" class="text-sm text-ink-400 text-center py-8">-</div>
      <div v-else class="flex items-end gap-1.5 h-44 overflow-x-auto scroll-thin">
        <div v-for="d in data.daily" :key="d.date" class="flex flex-col items-center gap-1 min-w-[34px] flex-1">
          <div class="w-full rounded-t-md bg-brand-500/80 hover:bg-brand-600 transition relative group" :style="{ height: `${Math.max(4, (d.revenue / maxDaily) * 140)}px` }">
            <div class="absolute -top-7 left-1/2 -translate-x-1/2 hidden group-hover:block bg-inverse text-white text-[10px] rounded px-1.5 py-0.5 whitespace-nowrap z-10">
              {{ money(d.revenue) }} · {{ d.orders }}
            </div>
          </div>
          <span class="text-[9px] text-ink-400">{{ d.date }}</span>
        </div>
      </div>
    </div>

    <div class="grid lg:grid-cols-2 gap-5 items-start">
      <div class="card p-6">
        <h3 class="font-extrabold text-ink-900 mb-4">{{ t('admin.topProducts') }}</h3>
        <div v-if="!data?.top_products?.length" class="text-sm text-ink-400 text-center py-6">-</div>
        <div v-else class="divide-y divide-ink-100">
          <div v-for="(p, i) in data.top_products" :key="i" class="py-2.5 flex items-center gap-3 text-sm">
            <span class="w-6 h-6 rounded-full bg-brand-100 text-brand-700 text-xs font-bold flex items-center justify-center shrink-0">{{ i + 1 }}</span>
            <div class="flex-1 min-w-0 line-clamp-1">{{ p.title_en || p.title_ko }}</div>
            <span class="text-xs text-ink-400">×{{ p.qty }}</span>
            <span class="font-bold text-ink-800">{{ money(p.revenue) }}</span>
          </div>
        </div>
      </div>

      <div class="card p-6">
        <h3 class="font-extrabold text-ink-900 mb-4">{{ t('admin.pricingRules') }}</h3>
        <div class="mb-4">
          <span class="label">{{ t('admin.globalMarkup') }}</span>
          <input v-model.number="globalMarkup" type="number" step="0.5" min="0" class="input" />
        </div>
        <div class="max-h-72 overflow-y-auto scroll-thin pr-1 space-y-2">
          <div v-for="c in cats || []" :key="c.id" class="flex items-center gap-3 text-sm">
            <span class="flex-1 text-ink-700 font-medium truncate">{{ c.name_en }}</span>
            <input
              v-model="catMarkups[c.id]"
              type="number"
              step="0.5"
              min="0"
              class="input !w-24 !py-1.5 text-sm"
              :placeholder="t('products.all')"
            />
            <span class="text-xs text-ink-300 w-8">%</span>
          </div>
        </div>
        <button class="btn-primary w-full mt-4 text-sm" @click="savePricing">{{ t('admin.apply') }}</button>
      </div>
    </div>
  </div>
</template>
