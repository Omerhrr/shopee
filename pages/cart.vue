<script setup lang="ts">
const { t, tr } = useI18n()
const money = useMoney()
const cart = useCartStore()
const toast = useToastState()

onMounted(() => cart.load())

const freeThreshold = 50000
const shipping = computed(() => (cart.subtotal >= freeThreshold || cart.subtotal === 0 ? 0 : 2500))
const remaining = computed(() => Math.max(0, freeThreshold - cart.subtotal))

const setQty = (slug: string, q: number) => cart.setQty(slug, q)

useHead({ title: () => t('cart.title') })
</script>

<template>
  <div class="max-w-5xl mx-auto px-4 py-10">
    <h1 class="text-2xl md:text-3xl font-extrabold text-ink-900 mb-8">{{ t('cart.title') }}</h1>

    <div v-if="!cart.items.length" class="card p-12 text-center">
      <svg class="w-14 h-14 mx-auto text-ink-200 mb-4" style="width:56px;height:56px" fill="none" stroke="currentColor" stroke-width="1.2" viewBox="0 0 24 24"><path d="M6 6h15l-1.5 9h-12L5 3H2" /><circle cx="9" cy="20" r="1.6" /><circle cx="18" cy="20" r="1.6" /></svg>
      <p class="text-ink-400 mb-5">{{ t('cart.empty') }}</p>
      <NuxtLink to="/products" class="btn-primary">{{ t('cart.continue') }}</NuxtLink>
    </div>

    <div v-else class="grid lg:grid-cols-3 gap-6 items-start">
      <div class="lg:col-span-2 card divide-y divide-ink-100">
        <div v-for="item in cart.items" :key="item.slug" class="p-4 flex gap-4 items-center">
          <NuxtLink :to="`/products/${item.slug}`" class="w-20 h-20 rounded-xl overflow-hidden bg-ink-100 shrink-0">
            <SmartImage :src="item.image || null" :alt="item.title_en || item.title_ko" />
          </NuxtLink>
          <div class="flex-1 min-w-0">
            <NuxtLink :to="`/products/${item.slug}`" class="font-semibold text-sm text-ink-800 hover:text-brand-700 line-clamp-2 block">
              {{ tr(item, 'title') }}
            </NuxtLink>
            <div class="mt-2 flex items-center gap-3">
              <div class="flex items-center border border-ink-200 rounded-lg overflow-hidden text-sm">
                <button class="w-8 h-8 hover:bg-ink-50 text-ink-500" @click="setQty(item.slug, item.quantity - 1)">−</button>
                <span class="w-8 text-center font-semibold">{{ item.quantity }}</span>
                <button class="w-8 h-8 hover:bg-ink-50 text-ink-500" @click="setQty(item.slug, item.quantity + 1)">+</button>
              </div>
              <button class="text-xs text-rose-500 hover:text-rose-700 font-semibold" @click="cart.remove(item.slug)">{{ t('cart.remove') }}</button>
            </div>
          </div>
          <div class="text-right font-extrabold text-ink-900">{{ money(item.price_sell * item.quantity) }}</div>
        </div>
      </div>

      <div class="card p-5 space-y-3">
        <h3 class="font-extrabold text-ink-900">{{ t('cart.checkout') }}</h3>
        <div class="flex justify-between text-sm">
          <span class="text-ink-500">{{ t('cart.subtotal') }}</span>
          <span class="font-semibold">{{ money(cart.subtotal) }}</span>
        </div>
        <div class="flex justify-between text-sm">
          <span class="text-ink-500">{{ t('cart.shipping') }}</span>
          <span class="font-semibold" :class="shipping === 0 ? 'text-emerald-600' : ''">{{ shipping === 0 ? t('cart.free') : money(shipping) }}</span>
        </div>
        <p v-if="remaining > 0" class="text-xs bg-amber-50 text-amber-700 rounded-lg px-3 py-2">
          {{ t('cart.freeShippingHint', { amount: money(remaining) }) }}
        </p>
        <div class="border-t border-ink-100 pt-3 flex justify-between">
          <span class="font-bold">{{ t('cart.total') }}</span>
          <span class="font-extrabold text-lg text-brand-700">{{ money(cart.subtotal + shipping) }}</span>
        </div>
        <NuxtLink to="/checkout" class="btn-primary w-full !py-3">{{ t('cart.checkout') }}</NuxtLink>
        <NuxtLink to="/products" class="btn-secondary w-full">{{ t('cart.continue') }}</NuxtLink>
      </div>
    </div>
  </div>
</template>
