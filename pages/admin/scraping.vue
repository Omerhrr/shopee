<script setup lang="ts">
import type { ScrapeLogRow, AdminSource } from '~~/types/checkout'

definePageMeta({ layout: 'admin' })
const { t } = useI18n()
const adminApi = useAdminApi()
const toast = useToastState()

const { data: sched, refresh: refreshSched } = await useAsyncData('admin-scrape-sched', async () =>
  await adminApi<{ interval_minutes: number; enabled: boolean; max_products_per_run: number; next_runs: Record<string, string | null> }>('/admin/scrape/schedule')
)

const { data: logs, refresh: refreshLogs } = await useAsyncData('admin-scrape-logs', async () =>
  await adminApi<ScrapeLogRow[]>('/admin/scrape/logs', { params: { limit: 30 } })
)

const { data: enabledSources, refresh: refreshSources } = await useAsyncData('admin-scrape-sources', async () =>
  await adminApi<AdminSource[]>('/admin/sources', { params: { enabled: 'true' } })
)

const form = reactive({ interval_minutes: 360, enabled: true, max_products_per_run: 10 })
watchEffect(() => {
  if (sched.value) {
    form.interval_minutes = sched.value.interval_minutes
    form.enabled = sched.value.enabled
    form.max_products_per_run = sched.value.max_products_per_run
  }
})

const saveSched = async () => {
  await adminApi('/admin/scrape/schedule', { method: 'PUT', body: { ...form } })
  toast(t('admin.saved'))
  refreshSched()
}

const running = ref(false)
const runAll = async () => {
  running.value = true
  toast(t('admin.scrapingAll'))
  try {
    await adminApi('/admin/scrape/run-all', { method: 'POST' })
    toast(t('admin.saved'))
    refreshLogs()
    refreshSched()
    refreshSources()
  } catch {
    toast(t('admin.error'))
  } finally {
    running.value = false
  }
}

// per-source sync
const scrapingId = ref(0)
const syncOne = async (s: AdminSource) => {
  scrapingId.value = s.id
  try {
    const r = await adminApi<{ status: string; new: number; updated: number; message: string }>(`/admin/sources/${s.id}/scrape`, { method: 'POST' })
    toast(`${s.name}: ${r.status} · +${r.new}, ~${r.updated}`)
    refreshLogs()
    refreshSources()
  } catch {
    toast(t('admin.error'))
  } finally {
    scrapingId.value = 0
  }
}

const statusBadge = (s: AdminSource) =>
  s.status === 'ok' ? 'bg-emerald-50 text-emerald-700' : s.status === 'error' ? 'bg-rose-50 text-rose-700' : 'bg-ink-100 text-ink-500'

const fmt = (s: string | null | undefined) => (s ? new Date(s).toLocaleString() : '-')

useHead({ title: () => `Shopee · ${t('admin.scraping')}` })
</script>

<template>
  <div>
    <div class="flex items-center justify-between gap-3 mb-6">
      <h1 class="text-2xl font-extrabold text-ink-900">{{ t('admin.scraping') }}</h1>
      <button class="btn-secondary text-sm" :disabled="running" @click="runAll">{{ running ? '…' : t('admin.runNow') }}</button>
    </div>

    <div class="grid lg:grid-cols-2 gap-5 items-start mb-5">
      <!-- Schedule -->
      <div class="card p-6">
        <h3 class="font-extrabold text-ink-900 mb-4">{{ t('admin.schedule') }}</h3>
        <div class="space-y-4">
          <label class="flex items-center gap-2 text-sm font-semibold text-ink-700">
            <input v-model="form.enabled" type="checkbox" class="w-4 h-4 accent-brand-600" />
            {{ t('admin.enabled') }}
          </label>
          <div class="grid grid-cols-2 gap-4">
            <div>
              <span class="label">{{ t('admin.interval') }}</span>
              <input v-model.number="form.interval_minutes" type="number" min="5" class="input" />
            </div>
            <div>
              <span class="label">{{ t('admin.maxPerRun') }}</span>
              <input v-model.number="form.max_products_per_run" type="number" min="1" max="50" class="input" />
            </div>
          </div>
          <div class="flex items-center justify-between">
            <button class="btn-primary text-sm" @click="saveSched">{{ t('admin.save') }}</button>
          </div>
          <div class="text-xs text-ink-400 pt-2 border-t border-ink-100">
            <span class="font-semibold">{{ t('admin.nextRun') }}:</span>
            {{ fmt(sched?.next_runs?.scrape_all) }}
          </div>
        </div>
      </div>

      <!-- Logs -->
      <div class="card p-6">
        <h3 class="font-extrabold text-ink-900 mb-4">{{ t('admin.logs') }}</h3>
        <div v-if="!logs || !logs.length" class="text-sm text-ink-400 py-6 text-center">{{ t('admin.noLogs') }}</div>
        <div v-else class="space-y-2.5 max-h-96 overflow-y-auto scroll-thin pr-1">
          <div v-for="l in logs" :key="l.id" class="rounded-xl border border-ink-100 p-3 text-sm">
            <div class="flex items-center gap-2 flex-wrap">
              <span class="font-bold text-ink-800">{{ l.source_name }}</span>
              <span class="badge text-[10px]" :class="l.status === 'ok' ? 'bg-emerald-50 text-emerald-700' : 'bg-rose-50 text-rose-700'">{{ l.status }}</span>
              <span class="badge bg-ink-100 text-ink-500 text-[10px]">{{ l.trigger }}</span>
              <span class="ml-auto text-[11px] text-ink-400">{{ l.started_at ? new Date(l.started_at).toLocaleString() : '' }}</span>
            </div>
            <div class="text-xs text-ink-500 mt-1">
              <span class="text-emerald-600 font-semibold">+{{ l.new_products }}</span> {{ t('admin.new') }} ·
              <span class="font-semibold">{{ l.updated_products }}</span> {{ t('admin.updated') }}
              - {{ l.message }}
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- Enabled source health -->
    <div class="card p-6">
      <h3 class="font-extrabold text-ink-900 mb-4">{{ t('admin.sourceHealth') }}</h3>
      <div v-if="!enabledSources || !enabledSources.length" class="text-sm text-ink-400 py-6 text-center">
        {{ t('admin.noEnabledSources') }}
      </div>
      <div v-else class="overflow-x-auto scroll-thin">
        <table class="w-full text-sm min-w-[700px]">
          <thead>
            <tr class="text-left text-xs uppercase tracking-wider text-ink-400 border-b border-ink-100">
              <th class="px-3 py-2.5">{{ t('admin.name') }}</th>
              <th class="px-3 py-2.5">{{ t('admin.status') }}</th>
              <th class="px-3 py-2.5">{{ t('admin.lastScraped') }}</th>
              <th class="px-3 py-2.5">{{ t('admin.lastMessage') }}</th>
              <th class="px-3 py-2.5 text-right">{{ t('admin.actions') }}</th>
            </tr>
          </thead>
          <tbody class="divide-y divide-ink-50">
            <tr v-for="s in enabledSources" :key="s.id" class="hover:bg-ink-50/50">
              <td class="px-3 py-2.5 font-semibold text-ink-800">{{ s.name }}</td>
              <td class="px-3 py-2.5">
                <span class="badge text-[10px]" :class="statusBadge(s)">{{ s.status }}</span>
              </td>
              <td class="px-3 py-2.5 text-xs text-ink-400">{{ fmt(s.last_scraped_at) }}</td>
              <td class="px-3 py-2.5 text-xs text-ink-500 max-w-[320px] truncate">{{ s.last_error || '-' }}</td>
              <td class="px-3 py-2.5 text-right">
                <button class="btn-ghost text-xs text-brand-700" :disabled="scrapingId === s.id" @click="syncOne(s)">
                  {{ scrapingId === s.id ? '…' : t('admin.scrapeNow') }}
                </button>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>
  </div>
</template>
