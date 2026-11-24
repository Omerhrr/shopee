<script setup lang="ts">
import type { AdminOrder } from '~~/types/checkout'

definePageMeta({ layout: 'admin' })
const { t } = useI18n()
const money = useMoney()
const adminApi = useAdminApi()
const toast = useToastState()

const status = ref('')
const q = ref('')
const page = ref(1)

const { data, refresh } = await useAsyncData(
  'admin-orders',
  async () =>
    await adminApi<{ items: AdminOrder[]; total: number; pages: number }>('/admin/orders', {
      params: { status: status.value || undefined, q: q.value || undefined, page: page.value, per_page: 20 }
    }),
  { watch: [status, q, page] }
)

const STATUSES = ['pending', 'paid', 'packed', 'shipped', 'delivered', 'cancelled']

const setStatus = async (o: AdminOrder, s: string) => {
  await adminApi(`/admin/orders/${o.id}/status`, { method: 'PUT', body: { status: s } })
  toast(t('admin.saved'))
  refresh()
}

const detail = ref<AdminOrder | null>(null)

const badge = (s: string) =>
  ({
    pending: 'bg-amber-100 text-amber-800 dark:bg-amber-500/15 dark:text-amber-300',
    paid: 'bg-emerald-50 text-emerald-700 dark:bg-emerald-500/15 dark:text-emerald-300',
    packed: 'bg-sky-50 text-sky-700 dark:bg-sky-500/15 dark:text-sky-300',
    shipped: 'bg-sky-100 text-sky-800 dark:bg-sky-500/15 dark:text-sky-300',
    delivered: 'bg-emerald-100 text-emerald-800 dark:bg-emerald-500/15 dark:text-emerald-300',
    cancelled: 'bg-rose-50 text-rose-700 dark:bg-rose-500/15 dark:text-rose-300'
  }[s] || 'bg-ink-100 text-ink-500')

useHead({ title: () => t('admin.orders') })
</script>

<template>
  <div>
    <h1 class="text-2xl font-extrabold text-ink-900 mb-5">{{ t('admin.orders') }} <span class="text-ink-400 text-lg font-bold">({{ data?.total ?? 0 }})</span></h1>

    <div class="flex flex-wrap gap-2 mb-4">
      <input v-model="q" :placeholder="t('admin.searchOrders')" class="input max-w-xs" />
      <select v-model="status" class="input !w-auto">
        <option value="">{{ t('admin.allOrderStatuses') }}</option>
        <option v-for="s in STATUSES" :key="s" :value="s">{{ t(`order.statuses.${s}`) }}</option>
      </select>
    </div>

    <div class="card overflow-x-auto scroll-thin">
      <table class="w-full text-sm min-w-[820px]">
        <thead>
          <tr class="text-left text-xs uppercase tracking-wider text-ink-400 border-b border-ink-100">
            <th class="px-4 py-3">{{ t('admin.orderNo') }}</th>
            <th class="px-3 py-3">{{ t('admin.customer') }}</th>
            <th class="px-3 py-3">{{ t('admin.itemsN', { n: '' }) }}</th>
            <th class="px-3 py-3">{{ t('admin.orderTotal') }}</th>
            <th class="px-3 py-3">{{ t('admin.orderProfit') }}</th>
            <th class="px-3 py-3">{{ t('admin.status') }}</th>
            <th class="px-3 py-3">{{ t('admin.date') }}</th>
            <th class="px-3 py-3 text-right">{{ t('admin.actions') }}</th>
          </tr>
        </thead>
        <tbody class="divide-y divide-ink-50">
          <tr v-for="o in data?.items || []" :key="o.id" class="hover:bg-ink-50/50">
            <td class="px-4 py-3 font-bold text-ink-800">{{ o.order_number }}</td>
            <td class="px-3 py-3">
              <div class="font-semibold text-ink-700">{{ o.customer_name }}</div>
              <div class="text-xs text-ink-400">{{ o.email || o.phone }}</div>
            </td>
            <td class="px-3 py-3 text-ink-500">{{ o.items.length }}</td>
            <td class="px-3 py-3 font-bold">{{ money(o.total) }}</td>
            <td class="px-3 py-3 text-emerald-600 font-semibold">{{ money(o.profit) }}</td>
            <td class="px-3 py-3">
              <select class="input !w-auto !py-1.5 text-xs" :value="o.status" @change="setStatus(o, ($event.target as HTMLSelectElement).value)">
                <option v-for="s in STATUSES" :key="s" :value="s">{{ t(`order.statuses.${s}`) }}</option>
              </select>
            </td>
            <td class="px-3 py-3 text-xs text-ink-400">{{ o.created_at ? new Date(o.created_at).toLocaleDateString() : '' }}</td>
            <td class="px-3 py-3 text-right">
              <button class="btn-ghost text-xs" @click="detail = o">{{ t('admin.view') }}</button>
            </td>
          </tr>
        </tbody>
      </table>
    </div>

    <PaginationNav v-if="data" :page="data.page" :pages="data.pages" @go="(p) => (page = p)" />

    <AdminModal :open="!!detail" :title="`${t('admin.orderNo')} ${detail?.order_number}`" wide @close="detail = null">
      <div v-if="detail">
        <div class="flex flex-wrap gap-2 mb-4">
          <span class="badge" :class="badge(detail.status)">{{ t(`order.statuses.${detail.status}`) }}</span>
          <span class="badge bg-ink-100 text-ink-600">{{ detail.payment_method }}</span>
          <span class="badge bg-ink-100 text-ink-600">{{ detail.locale.toUpperCase() }}</span>
        </div>
        <div class="card p-4 text-sm text-ink-600 mb-4">
          <div class="font-semibold text-ink-800 mb-1">{{ detail.customer_name }} · {{ detail.phone }}</div>
          <div>{{ detail.address1 }} {{ detail.address2 }}, {{ detail.city }} {{ detail.postal_code }}</div>
          <div v-if="detail.memo" class="text-ink-400 mt-1">memo: {{ detail.memo }}</div>
        </div>
        <div class="divide-y divide-ink-100 border border-ink-100 rounded-xl mb-4">
          <div v-for="i in detail.items" :key="i.id" class="p-3 flex gap-3 items-center text-sm">
            <div class="w-10 h-10 rounded-lg overflow-hidden bg-ink-100 shrink-0">
              <img v-if="i.image" :src="i.image" :alt="i.title_en" class="w-full h-full object-cover" />
            </div>
            <div class="flex-1 min-w-0">
              <div class="font-semibold line-clamp-1">{{ i.title_en || i.title_ko }}</div>
              <div class="text-xs text-ink-400">{{ money(i.unit_sell) }} × {{ i.quantity }} (cost {{ money(i.unit_cost) }})</div>
            </div>
            <div class="font-bold">{{ money(i.unit_sell * i.quantity) }}</div>
          </div>
        </div>
        <div class="grid grid-cols-2 gap-2 text-sm">
          <div class="flex justify-between p-2"><span class="text-ink-500">{{ t('cart.subtotal') }}</span><span>{{ money(detail.subtotal) }}</span></div>
          <div class="flex justify-between p-2"><span class="text-ink-500">{{ t('cart.shipping') }}</span><span>{{ money(detail.shipping) }}</span></div>
          <div class="flex justify-between p-2 font-bold"><span>{{ t('admin.orderTotal') }}</span><span>{{ money(detail.total) }}</span></div>
          <div class="flex justify-between p-2 text-emerald-600 font-bold"><span>{{ t('admin.orderProfit') }}</span><span>{{ money(detail.profit) }}</span></div>
        </div>
      </div>
    </AdminModal>
  </div>
</template>
