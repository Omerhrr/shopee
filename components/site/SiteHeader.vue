<script setup lang="ts">
const { t, locale, setLocale } = useI18n()
const { siteName, mode, toggleMode } = useTheme()
const money = useMoney()
const cart = useCartStore()
const route = useRoute()
const router = useRouter()

const q = ref((route.query.q as string) || '')
const mobileOpen = ref(false)

watch(
  () => route.query.q,
  (v) => {
    q.value = (v as string) || ''
  }
)

const submitSearch = () => {
  router.push({ path: '/products', query: q.value ? { q: q.value } : {} })
  mobileOpen.value = false
}

const switchLocale = (l: 'en' | 'ko') => setLocale(l)
</script>

<template>
  <header class="sticky top-0 z-40 bg-surface/95 backdrop-blur border-b border-ink-100">
    <div class="bg-inverse text-white text-xs">
      <div class="max-w-7xl mx-auto px-4 h-8 flex items-center justify-between gap-4">
        <span class="hidden sm:inline">{{ t('nav.shipsFromKorea') }}</span>
        <span class="sm:hidden">{{ t('nav.shipsFromKorea') }}</span>
        <span class="font-medium text-accent-300">{{ t('nav.freeShipping', { amount: money(50000) }) }}</span>
      </div>
    </div>

    <div class="max-w-7xl mx-auto px-4 h-16 flex items-center gap-3 md:gap-4">
      <NuxtLink to="/" class="flex items-center gap-2 shrink-0" aria-label="Home">
        <span class="w-9 h-9 rounded-xl bg-brand-600 text-white font-extrabold text-lg flex items-center justify-center shadow-pop">{{ siteName.charAt(0).toUpperCase() }}</span>
        <span class="text-xl font-extrabold tracking-tight text-ink-900">{{ siteName }}</span>
      </NuxtLink>

      <form class="flex-1 hidden md:block max-w-xl" @submit.prevent="submitSearch">
        <div class="relative">
          <input
            v-model="q"
            :placeholder="t('nav.searchPlaceholder')"
            class="input pl-10 rounded-full"
            type="search"
            :aria-label="t('nav.searchPlaceholder')"
          />
          <svg class="w-4.5 h-4.5 absolute left-3.5 top-3 text-ink-400" style="width:18px;height:18px" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><circle cx="11" cy="11" r="7" /><path d="m21 21-4.3-4.3" /></svg>
        </div>
      </form>

      <nav class="flex items-center gap-1 ml-auto">
        <div class="hidden lg:flex items-center mr-2 text-sm font-semibold">
          <NuxtLink to="/" class="px-3 py-2 rounded-lg hover:bg-ink-100 text-ink-700">{{ t('nav.home') }}</NuxtLink>
          <NuxtLink to="/products" class="px-3 py-2 rounded-lg hover:bg-ink-100 text-ink-700">{{ t('nav.products') }}</NuxtLink>
        </div>

        <button
          class="btn-ghost"
          :aria-label="mode === 'dark' ? t('nav.lightMode') : t('nav.darkMode')"
          :title="mode === 'dark' ? t('nav.lightMode') : t('nav.darkMode')"
          @click="toggleMode"
        >
          <svg v-if="mode === 'dark'" style="width:20px;height:20px" fill="none" stroke="currentColor" stroke-width="1.8" viewBox="0 0 24 24"><circle cx="12" cy="12" r="4" /><path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4" /></svg>
          <svg v-else style="width:20px;height:20px" fill="none" stroke="currentColor" stroke-width="1.8" viewBox="0 0 24 24"><path d="M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8z" /></svg>
        </button>

        <div class="flex items-center rounded-full border border-ink-200 overflow-hidden text-xs font-bold" role="group" aria-label="Language">
          <button
            class="px-2.5 py-1.5 transition whitespace-nowrap"
            :class="locale === 'en' ? 'bg-inverse text-white' : 'text-ink-500 hover:bg-ink-100'"
            @click="switchLocale('en')"
          >EN</button>
          <button
            class="px-2.5 py-1.5 transition whitespace-nowrap"
            :class="locale === 'ko' ? 'bg-inverse text-white' : 'text-ink-500 hover:bg-ink-100'"
            @click="switchLocale('ko')"
          >한국어</button>
        </div>

        <NuxtLink to="/cart" class="relative btn-ghost" aria-label="Cart">
          <svg style="width:22px;height:22px" fill="none" stroke="currentColor" stroke-width="1.8" viewBox="0 0 24 24"><path d="M6 6h15l-1.5 9h-12L5 3H2" /><circle cx="9" cy="20" r="1.6" /><circle cx="18" cy="20" r="1.6" /></svg>
          <span v-if="cart.count" class="absolute -top-0.5 -right-0.5 bg-brand-600 text-white text-[10px] font-bold rounded-full min-w-[18px] h-[18px] flex items-center justify-center px-1">{{ cart.count }}</span>
        </NuxtLink>

        <button class="btn-ghost lg:hidden" aria-label="Menu" @click="mobileOpen = !mobileOpen">
          <svg style="width:22px;height:22px" fill="none" stroke="currentColor" stroke-width="1.8" viewBox="0 0 24 24"><path d="M4 6h16M4 12h16M4 18h16" /></svg>
        </button>
      </nav>
    </div>

    <div v-if="mobileOpen" class="md:hidden border-t border-ink-100 px-4 py-3 space-y-3 bg-surface">
      <form @submit.prevent="submitSearch">
        <input v-model="q" :placeholder="t('nav.searchPlaceholder')" class="input rounded-full" type="search" />
      </form>
      <div class="flex gap-2">
        <NuxtLink to="/" class="btn-secondary flex-1" @click="mobileOpen = false">{{ t('nav.home') }}</NuxtLink>
        <NuxtLink to="/products" class="btn-secondary flex-1" @click="mobileOpen = false">{{ t('nav.products') }}</NuxtLink>
      </div>
    </div>
  </header>
</template>
