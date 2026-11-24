<script setup lang="ts">
import type { CheckoutIn } from '~~/types/checkout'

const { t, tr } = useI18n()
const money = useMoney()
const cart = useCartStore()
const api = useApi()
const toast = useToastState()
const router = useRouter()

onMounted(() => cart.load())

const form = reactive({
  name: '',
  phone: '',
  email: '',
  address1: '',
  address2: '',
  city: '',
  postal_code: '',
  memo: ''
})
const payment = ref<'card' | 'bank'>('card')
const placing = ref(false)

const freeThreshold = 50000
const shipping = computed(() => (cart.subtotal >= freeThreshold ? 0 : 2500))

const valid = computed(() => form.name && form.phone && form.address1 && cart.items.length)

const placeOrder = async () => {
  if (!valid.value) return
  placing.value = true
  try {
    const body: CheckoutIn = {
      items: cart.items.map((i) => ({ slug: i.slug, quantity: i.quantity })),
      customer: { ...form },
      payment_method: payment.value,
      locale: useState<string>('locale').value
    }
    const res = await api<{ order_number: string }>('/orders', { method: 'POST', body })
    cart.clear()
    toast(t('checkout.success'))
    router.push(`/orders/${res.order_number}`)
  } catch (e: any) {
    toast(e?.data?.detail || t('admin.error'))
  } finally {
    placing.value = false
  }
}

useHead({ title: () => t('checkout.title') })
</script>

<template>
  <div class="max-w-6xl mx-auto px-4 py-10">
    <h1 class="text-2xl md:text-3xl font-extrabold text-ink-900 mb-8">{{ t('checkout.title') }}</h1>

    <div v-if="!cart.items.length" class="card p-12 text-center">
      <p class="text-ink-400 mb-5">{{ t('cart.empty') }}</p>
      <NuxtLink to="/products" class="btn-primary">{{ t('cart.continue') }}</NuxtLink>
    </div>

    <div v-else class="grid lg:grid-cols-3 gap-6 items-start">
      <div class="lg:col-span-2 space-y-5">
        <div class="card p-5">
          <h3 class="font-extrabold text-ink-900 mb-4">{{ t('checkout.contact') }}</h3>
          <div class="grid md:grid-cols-2 gap-4">
            <div><label class="label" for="co-name">{{ t('checkout.name') }} *</label><input id="co-name" v-model="form.name" class="input" /></div>
            <div><label class="label" for="co-phone">{{ t('checkout.phone') }} *</label><input id="co-phone" v-model="form.phone" class="input" /></div>
            <div class="md:col-span-2"><label class="label" for="co-email">{{ t('checkout.email') }}</label><input id="co-email" v-model="form.email" type="email" class="input" /></div>
          </div>
        </div>

        <div class="card p-5">
          <h3 class="font-extrabold text-ink-900 mb-4">{{ t('checkout.address') }}</h3>
          <div class="grid md:grid-cols-2 gap-4">
            <div class="md:col-span-2"><label class="label" for="co-addr1">{{ t('checkout.address1') }} *</label><input id="co-addr1" v-model="form.address1" class="input" /></div>
            <div class="md:col-span-2"><label class="label" for="co-addr2">{{ t('checkout.address2') }}</label><input id="co-addr2" v-model="form.address2" class="input" /></div>
            <div><label class="label" for="co-city">{{ t('checkout.city') }}</label><input id="co-city" v-model="form.city" class="input" /></div>
            <div><label class="label" for="co-postal">{{ t('checkout.postal') }}</label><input id="co-postal" v-model="form.postal_code" class="input" /></div>
            <div class="md:col-span-2"><label class="label" for="co-memo">{{ t('checkout.memo') }}</label><input id="co-memo" v-model="form.memo" class="input" /></div>
          </div>
        </div>

        <div class="card p-5">
          <h3 class="font-extrabold text-ink-900 mb-4">{{ t('checkout.payment') }}</h3>
          <div class="space-y-3">
            <label class="flex items-start gap-3 p-3.5 rounded-xl border cursor-pointer transition" :class="payment === 'card' ? 'border-brand-500 bg-brand-50' : 'border-ink-200'">
              <input v-model="payment" type="radio" value="card" class="mt-1 accent-brand-600" />
              <div>
                <div class="font-semibold text-sm">{{ t('checkout.card') }}</div>
                <div class="text-xs text-ink-400 mt-0.5">{{ t('checkout.cardNote') }}</div>
              </div>
            </label>
            <label class="flex items-start gap-3 p-3.5 rounded-xl border cursor-pointer transition" :class="payment === 'bank' ? 'border-brand-500 bg-brand-50' : 'border-ink-200'">
              <input v-model="payment" type="radio" value="bank" class="mt-1 accent-brand-600" />
              <div>
                <div class="font-semibold text-sm">{{ t('checkout.bank') }}</div>
                <div class="text-xs text-ink-400 mt-0.5">{{ t('checkout.bankNote') }}</div>
              </div>
            </label>
          </div>
        </div>
      </div>

      <div class="card p-5 lg:sticky lg:top-24">
        <h3 class="font-extrabold text-ink-900 mb-4">{{ t('checkout.summary') }}</h3>
        <div class="space-y-3 max-h-56 overflow-y-auto scroll-thin pr-1">
          <div v-for="i in cart.items" :key="i.slug" class="flex gap-3 items-center text-sm">
            <div class="w-11 h-11 rounded-lg overflow-hidden bg-ink-100 shrink-0">
              <SmartImage :src="i.image || null" :alt="i.title_en || i.title_ko" />
            </div>
            <div class="flex-1 min-w-0">
              <div class="font-medium line-clamp-1">{{ tr(i, 'title') }}</div>
              <div class="text-ink-400 text-xs">× {{ i.quantity }}</div>
            </div>
            <div class="font-semibold">{{ money(i.price_sell * i.quantity) }}</div>
          </div>
        </div>
        <div class="border-t border-ink-100 mt-4 pt-4 space-y-2 text-sm">
          <div class="flex justify-between"><span class="text-ink-500">{{ t('cart.subtotal') }}</span><span>{{ money(cart.subtotal) }}</span></div>
          <div class="flex justify-between"><span class="text-ink-500">{{ t('cart.shipping') }}</span><span>{{ shipping === 0 ? t('cart.free') : money(shipping) }}</span></div>
          <div class="flex justify-between border-t border-ink-100 pt-2 text-base font-extrabold">
            <span>{{ t('cart.total') }}</span><span class="text-brand-700">{{ money(cart.subtotal + shipping) }}</span>
          </div>
        </div>
        <button class="btn-primary w-full !py-3 mt-4" :disabled="!valid || placing" @click="placeOrder">
          {{ placing ? t('checkout.placing') : t('checkout.placeOrder') }}
        </button>
      </div>
    </div>
  </div>
</template>
