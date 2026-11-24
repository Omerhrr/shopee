<script setup lang="ts">
definePageMeta({ layout: 'admin' })
const { t } = useI18n()
const money = useMoney()
const adminApi = useAdminApi()
const toast = useToastState()

const { data, pending } = await useAsyncData('admin-dashboard', async () => await adminApi('/admin/dashboard'))

const runAll = async () => {
  toast(t('admin.scrapingAll'))
  try {
    await adminApi('/admin/scrape/run-all', { method: 'POST' })
    toast(t('admin.saved'))
    refreshNuxtData('admin-dashboard')
  } catch {
    toast(t('admin.error'))
  }
}

const runTrans = async () => {
  try {
    const r = await adminApi('/admin/translations/run', { method: 'POST' })
    toast(`${r.translated ?? 0} translated, ${r.failed ?? 0} failed`)
    refreshNuxtData('admin-dashboard')
  } catch {
    toast(t('admin.error'))
  }
}

useHead({ title: () => t('admin.dashboard') })
</script>

<template>
  <div>
    <div class="flex items-center justify-between mb-6">
      <h1 class="text-2xl font-extrabold text-ink-900">{{ t('admin.dashboard') }}</h1>
      <div class="flex gap-2">
        <button class="btn-secondary text-sm" @click="runAll">{{ t('admin.runAllSources') }}</button>
        <button class="btn-secondary text-sm" @click="runTrans">{{ t('admin.runTranslations') }}</button>
      </div>
    </div>

    <div v-if="pending && !data" class="text-ink-400">{{ t('products.loading') }}</div>
    <template v-else-if="data">
      <div class="grid grid-cols-2 lg:grid-cols-4 gap-4 mb-6">
        <StatCard :label="t('admin.revenueToday')" :value="money(data.revenue_today)" accent="brand" />
        <StatCard :label="t('admin.profitToday')" :value="money(data.profit_today)" accent="green" />
        <StatCard :label="t('admin.ordersToday')" :value="String(data.orders_today)" />
        <StatCard :label="t('admin.activeProducts')" :value="`${data.products_published} / ${data.products_total}`" />
        <StatCard :label="t('admin.sourcesEnabled')" :value="`${data.sources_enabled} / ${data.sources_total}`" />
        <StatCard :label="t('admin.pendingTranslations')" :value="String(data.products_pending_translation)" :accent="data.products_pending_translation ? 'red' : 'plain'" />
        <StatCard
          :label="t('admin.lastScrape')"
          :value="data.last_scrape?.at ? new Date(data.last_scrape.at).toLocaleString() : t('admin.never')"
          :hint="data.last_scrape?.source ? `${data.last_scrape.source} · ${data.last_scrape.status}` : ''"
        />
        <div class="card p-5">
          <div class="text-xs font-bold uppercase tracking-wider text-ink-400 mb-2">{{ t('admin.quickActions') }}</div>
          <div class="flex flex-col gap-2">
            <NuxtLink to="/admin/products" class="btn-secondary !py-2 text-sm text-left">{{ t('admin.addProduct') }}</NuxtLink>
            <NuxtLink to="/admin/sources" class="btn-secondary !py-2 text-sm text-left">{{ t('admin.sources') }}</NuxtLink>
          </div>
        </div>
      </div>

      <div v-if="data.last_scrape?.status === 'error'" class="card p-4 border-rose-200 bg-rose-50 text-sm text-rose-700 dark:border-rose-500/30 dark:bg-rose-500/10 dark:text-rose-300">
        <b>{{ data.last_scrape?.source }}</b> - {{ data.last_scrape?.message }}
      </div>
    </template>
  </div>
</template>
