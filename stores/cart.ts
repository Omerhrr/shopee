import { defineStore } from 'pinia'

export interface CartItem {
  slug: string
  title_ko: string
  title_en: string | null
  image: string
  price_sell: number
  quantity: number
}

export const useCartStore = defineStore('cart', () => {
  const items = ref<CartItem[]>([])
  const loaded = ref(false)

  const load = () => {
    if (import.meta.client && !loaded.value) {
      try {
        items.value = JSON.parse(localStorage.getItem('shopee_cart') || '[]')
      } catch {
        items.value = []
      }
      loaded.value = true
    }
  }

  const persist = () => {
    if (import.meta.client) localStorage.setItem('shopee_cart', JSON.stringify(items.value))
  }

  const add = (p: any, qty = 1) => {
    load()
    const found = items.value.find((i) => i.slug === p.slug)
    if (found) found.quantity = Math.min(99, found.quantity + qty)
    else
      items.value.push({
        slug: p.slug,
        title_ko: p.title_ko,
        title_en: p.title_en,
        image: (p.images || [])[0] || '',
        price_sell: p.price_sell,
        quantity: qty
      })
    persist()
  }

  const setQty = (slug: string, qty: number) => {
    const it = items.value.find((i) => i.slug === slug)
    if (!it) return
    it.quantity = Math.max(1, Math.min(99, qty))
    persist()
  }

  const remove = (slug: string) => {
    items.value = items.value.filter((i) => i.slug !== slug)
    persist()
  }

  const clear = () => {
    items.value = []
    persist()
  }

  const count = computed(() => items.value.reduce((s, i) => s + i.quantity, 0))
  const subtotal = computed(() => items.value.reduce((s, i) => s + i.price_sell * i.quantity, 0))

  return { items, load, add, setQty, remove, clear, count, subtotal }
})
