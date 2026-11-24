<script setup lang="ts">
const { t } = useI18n()
const { siteName } = useTheme()
const route = useRoute()
const token = useCookie<string | null>('shopee_admin_token')

const links = computed(() => [
  { to: '/admin', label: t('admin.dashboard'), icon: 'grid' },
  { to: '/admin/products', label: t('admin.products'), icon: 'box' },
  { to: '/admin/sources', label: t('admin.sources'), icon: 'link' },
  { to: '/admin/scraping', label: t('admin.scraping'), icon: 'refresh' },
  { to: '/admin/export', label: t('admin.export'), icon: 'upload' },
  { to: '/admin/orders', label: t('admin.orders'), icon: 'bag' },
  { to: '/admin/finance', label: t('admin.finance'), icon: 'coin' },
  { to: '/admin/settings', label: t('admin.settings'), icon: 'cog' }
])

const logout = () => {
  token.value = null
  navigateTo('/admin/login')
}

const isActive = (to: string) => (to === '/admin' ? route.path === '/admin' : route.path.startsWith(to))
</script>

<template>
  <div class="flex min-h-screen">
    <!-- Sidebar -->
    <aside class="w-60 shrink-0 bg-inverse text-ink-300 flex flex-col fixed inset-y-0 hidden md:flex">
      <div class="h-16 flex items-center gap-2 px-5 border-b border-white/10">
        <span class="w-8 h-8 rounded-lg bg-brand-600 text-white font-extrabold flex items-center justify-center">{{ (siteName || 'S').charAt(0).toUpperCase() }}</span>
        <div>
          <div class="text-white font-extrabold leading-none">{{ siteName }}</div>
          <div class="text-[10px] uppercase tracking-widest text-ink-400 mt-0.5">Admin</div>
        </div>
      </div>
      <nav class="flex-1 py-4 px-3 space-y-1 overflow-y-auto scroll-thin">
        <NuxtLink
          v-for="l in links"
          :key="l.to"
          :to="l.to"
          class="flex items-center gap-3 px-3.5 py-2.5 rounded-xl text-sm font-semibold transition"
          :class="isActive(l.to) ? 'bg-brand-600 text-white' : 'hover:bg-white/5 text-ink-300'"
        >
          <svg style="width:18px;height:18px" fill="none" stroke="currentColor" stroke-width="1.8" viewBox="0 0 24 24">
            <path v-if="l.icon === 'grid'" d="M4 4h7v7H4zM13 4h7v7h-7zM4 13h7v7H4zM13 13h7v7h-7z" />
            <path v-else-if="l.icon === 'box'" d="M21 8l-9-5-9 5v8l9 5 9-5V8zM3 8l9 5 9-5M12 13v8" />
            <path v-else-if="l.icon === 'link'" d="M10 14a5 5 0 0 0 7 0l3-3a5 5 0 0 0-7-7l-1.5 1.5M14 10a5 5 0 0 0-7 0l-3 3a5 5 0 0 0 7 7L12.5 19" />
            <path v-else-if="l.icon === 'refresh'" d="M21 12a9 9 0 1 1-2.6-6.3M21 4v5h-5" />
            <path v-else-if="l.icon === 'bag'" d="M6 8h12l1 13H5L6 8zM9 8a3 3 0 0 1 6 0" />
            <path v-else-if="l.icon === 'coin'" d="M12 2v20M17 6H9.5a3 3 0 0 0 0 6h5a3 3 0 0 1 0 6H6" />
            <path v-else-if="l.icon === 'upload'" d="M12 16V4M6 10l6-6 6 6M4 20h16" />
            <path v-else d="M12 15a3 3 0 1 0 0-6 3 3 0 0 0 0 6z M19.4 15a1.7 1.7 0 0 0 .3 1.9l.1.1a2 2 0 1 1-2.8 2.8l-.1-.1a1.7 1.7 0 0 0-1.9-.3 1.7 1.7 0 0 0-1 1.5V21a2 2 0 1 1-4 0v-.1a1.7 1.7 0 0 0-1-1.6 1.7 1.7 0 0 0-1.9.3l-.1.1a2 2 0 1 1-2.8-2.8l.1-.1a1.7 1.7 0 0 0 .3-1.9 1.7 1.7 0 0 0-1.5-1H3a2 2 0 1 1 0-4h.1a1.7 1.7 0 0 0 1.6-1 1.7 1.7 0 0 0-.3-1.9l-.1-.1a2 2 0 1 1 2.8-2.8l.1.1a1.7 1.7 0 0 0 1.9.3h.1a1.7 1.7 0 0 0 1-1.5V3a2 2 0 1 1 4 0v.1a1.7 1.7 0 0 0 1 1.5h.1a1.7 1.7 0 0 0 1.9-.3l.1-.1a2 2 0 1 1 2.8 2.8l-.1.1a1.7 1.7 0 0 0-.3 1.9v.1a1.7 1.7 0 0 0 1.5 1H21a2 2 0 1 1 0 4h-.1a1.7 1.7 0 0 0-1.5 1z" />
          </svg>
          {{ l.label }}
        </NuxtLink>
      </nav>
      <div class="p-3 border-t border-white/10 space-y-1">
        <NuxtLink to="/" class="flex items-center gap-3 px-3.5 py-2.5 rounded-xl text-sm font-semibold hover:bg-white/5">
          <svg style="width:18px;height:18px" fill="none" stroke="currentColor" stroke-width="1.8" viewBox="0 0 24 24"><path d="M3 11l9-8 9 8M5 10v10h14V10" /></svg>
          {{ t('admin.openStore') }}
        </NuxtLink>
        <button class="w-full flex items-center gap-3 px-3.5 py-2.5 rounded-xl text-sm font-semibold hover:bg-white/5 text-rose-300" @click="logout">
          <svg style="width:18px;height:18px" fill="none" stroke="currentColor" stroke-width="1.8" viewBox="0 0 24 24"><path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4M16 17l5-5-5-5M21 12H9" /></svg>
          {{ t('admin.logout') }}
        </button>
      </div>
    </aside>

    <!-- Mobile topbar: brand row (with storefront + sign-out actions) and a scrollable page-chip row -->
    <div class="md:hidden fixed top-0 inset-x-0 z-40 bg-inverse text-white shadow-lg">
      <div class="h-12 flex items-center justify-between px-4">
        <div class="flex items-center gap-2">
          <span class="w-7 h-7 rounded-lg bg-brand-600 font-extrabold flex items-center justify-center text-sm">{{ (siteName || 'S').charAt(0).toUpperCase() }}</span>
          <span class="font-bold">{{ siteName }} Admin</span>
        </div>
        <div class="flex items-center gap-1">
          <NuxtLink
            to="/"
            class="p-2 rounded-lg hover:bg-white/10 text-white/90"
            :title="t('admin.openStore')"
            :aria-label="t('admin.openStore')"
          >
            <svg style="width:18px;height:18px" fill="none" stroke="currentColor" stroke-width="1.8" viewBox="0 0 24 24"><path d="M3 11l9-8 9 8M5 10v10h14V10" /></svg>
          </NuxtLink>
          <button
            class="p-2 rounded-lg hover:bg-white/10 text-rose-300"
            :title="t('admin.logout')"
            :aria-label="t('admin.logout')"
            @click="logout"
          >
            <svg style="width:18px;height:18px" fill="none" stroke="currentColor" stroke-width="1.8" viewBox="0 0 24 24"><path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4M16 17l5-5-5-5M21 12H9" /></svg>
          </button>
        </div>
      </div>
      <div class="h-10 px-3 flex items-center gap-2 overflow-x-auto scroll-thin">
        <NuxtLink v-for="l in links" :key="l.to" :to="l.to" class="text-xs px-2.5 py-1.5 rounded-lg whitespace-nowrap" :class="isActive(l.to) ? 'bg-brand-600' : 'bg-white/10'">{{ l.label }}</NuxtLink>
      </div>
    </div>

    <div class="flex-1 md:ml-60 pt-[88px] md:pt-0 min-w-0">
      <div class="p-4 md:p-8 max-w-6xl">
        <slot />
      </div>
    </div>
  </div>
</template>
