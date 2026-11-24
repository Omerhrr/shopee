<script setup lang="ts">
const { t } = useI18n()
const money = useMoney()
const api = useApi()
const route = useRoute()

const { data: order, error } = await useAsyncData(`order-${route.params.number}`, async () =>
  await api(`/orders/${route.params.number}`)
)

const steps = ['pending', 'paid', 'packed', 'shipped', 'delivered'] as const
const stepIndex = computed(() => {
  if (!order.value) return -1
  if (order.value.status === 'cancelled') return -2
  return steps.indexOf(order.value.status as any)
})

useHead({ title: () => t('order.title', { n: route.params.number as string }) })
</script>

<template>
  <div class="max-w-3xl mx-auto px-4 py-10">
    <div v-if="error || !order" class="card p-12 text-center">
      <p class="text-ink-400">{{ t('order.notFound') }}</p>
    </div>

    <div v-else>
      <div class="card p-6 md:p-8 mb-6 text-center border-emerald-200 bg-emerald-50/40 dark:border-emerald-500/30 dark:bg-emerald-500/10">
        <div class="w-14 h-14 mx-auto bg-emerald-100 dark:bg-emerald-500/20 rounded-full flex items-center justify-center mb-3">
          <svg style="width:28px;height:28px" fill="none" stroke="#059669" stroke-width="2.5" viewBox="0 0 24 24"><path d="m5 13 4 4L19 7" /></svg>
        </div>
        <h1 class="text-xl md:text-2xl font-extrabold text-ink-900">{{ t('checkout.success') }}</h1>
        <p class="text-ink-500 mt-1">{{ t('order.title', { n: order.order_number }) }}</p>
      </div>

      <!-- Timeline -->
      <div class="card p-6 mb-6">
        <h3 class="font-extrabold text-ink-900 mb-5">{{ t('order.timeline') }}</h3>
        <div v-if="stepIndex === -2" class="text-rose-600 font-bold text-center py-2">{{ t('order.statuses.cancelled') }}</div>
        <div v-else class="flex items-center">
          <template v-for="(s, i) in steps" :key="s">
            <div class="flex flex-col items-center shrink-0">
              <div
                class="w-9 h-9 rounded-full flex items-center justify-center text-sm font-bold border-2 transition"
                :class="i <= stepIndex ? 'bg-brand-600 border-brand-600 text-white' : 'bg-surface border-ink-200 text-ink-300'"
              >
                <svg v-if="i < stepIndex" style="width:16px;height:16px" fill="none" stroke="currentColor" stroke-width="3" viewBox="0 0 24 24"><path d="m5 13 4 4L19 7" /></svg>
                <span v-else>{{ i + 1 }}</span>
              </div>
              <span class="text-[11px] mt-1.5 font-semibold text-ink-500 text-center w-16">{{ t(`order.statuses.${s}`) }}</span>
            </div>
            <div v-if="i < steps.length - 1" class="flex-1 h-0.5 mx-1 mb-5" :class="i < stepIndex ? 'bg-brand-600' : 'bg-ink-200'" />
          </template>
        </div>
      </div>

      <!-- Items -->
      <div class="card p-6 mb-6">
        <h3 class="font-extrabold text-ink-900 mb-4">{{ t('order.items') }}</h3>
        <div class="divide-y divide-ink-100">
          <div v-for="i in order.items" :key="i.id" class="py-3 flex gap-4 items-center">
            <div class="w-14 h-14 rounded-lg overflow-hidden bg-ink-100 shrink-0">
              <SmartImage :src="i.image || null" :alt="i.title_en || i.title_ko" />
            </div>
            <div class="flex-1 min-w-0">
              <div class="font-semibold text-sm line-clamp-1">{{ i.title_en || i.title_ko }}</div>
              <div class="text-xs text-ink-400">{{ money(i.unit_sell) }} × {{ i.quantity }}</div>
            </div>
            <div class="font-bold text-sm">{{ money(i.unit_sell * i.quantity) }}</div>
          </div>
        </div>
      </div>

      <!-- Summary -->
      <div class="card p-6 mb-8">
        <h3 class="font-extrabold text-ink-900 mb-4">{{ t('order.summary') }}</h3>
        <div class="space-y-2 text-sm">
          <div class="flex justify-between"><span class="text-ink-500">{{ t('cart.subtotal') }}</span><span>{{ money(order.subtotal) }}</span></div>
          <div class="flex justify-between"><span class="text-ink-500">{{ t('cart.shipping') }}</span><span>{{ order.shipping === 0 ? t('cart.free') : money(order.shipping) }}</span></div>
          <div class="flex justify-between border-t border-ink-100 pt-2 font-extrabold text-base">
            <span>{{ t('cart.total') }}</span><span class="text-brand-700">{{ money(order.total) }}</span>
          </div>
          <div class="flex justify-between text-ink-400 text-xs pt-1">
            <span>{{ order.customer_name }} · {{ order.address1 }} {{ order.address2 }}</span>
          </div>
        </div>
      </div>

      <div class="text-center">
        <NuxtLink to="/products" class="btn-secondary">{{ t('cart.continue') }}</NuxtLink>
      </div>
    </div>
  </div>
</template>
