<script setup lang="ts">
import { THEME_PRESETS, FONT_OPTIONS, deriveBrand } from '~~/composables/useTheme'

definePageMeta({ layout: 'admin' })
const { t } = useI18n()
const adminApi = useAdminApi()
const toast = useToastState()

const { data: settings } = await useAsyncData('admin-settings', async () => await adminApi<Record<string, any>>('/admin/settings'))

const form = reactive({
  site_name: 'Shopee',
  shipping_flat: 2500,
  free_shipping_threshold: 50000,
  // theme
  theme_primary: '#EA580C',
  theme_accent: '#F59E0B',
  theme_radius: 12,
  // fonts
  fonts_family: 'Inter',
  fonts_heading: 'Inter',
  fonts_base_size: 16,
  fonts_heading_weight: 800,
  // translation
  translate_provider: 'google_free',
  translate_api_key: '',
  translate_api_secret: '',
  translate_deepl_host: 'free',
  translate_libre_url: '',
  // downloads
  download_zip_enabled: true
})

watchEffect(() => {
  if (settings.value) Object.assign(form, settings.value)
})

const saveSettings = async (keys: Record<string, any>) => {
  await adminApi('/admin/settings', { method: 'PUT', body: keys })
  toast(t('admin.saved'))
}

const saveStore = () => saveSettings({ site_name: form.site_name, shipping_flat: Number(form.shipping_flat), free_shipping_threshold: Number(form.free_shipping_threshold) })
const saveTheme = () => saveSettings({ theme_primary: form.theme_primary, theme_accent: form.theme_accent, theme_radius: Number(form.theme_radius) })
const saveFonts = () => saveSettings({ fonts_family: form.fonts_family, fonts_heading: form.fonts_heading, fonts_base_size: Number(form.fonts_base_size), fonts_heading_weight: Number(form.fonts_heading_weight) })

// ----- live theme preview (uses the same palette engine as the storefront) -----
const previewVars = computed(() => {
  const brand = deriveBrand(form.theme_primary || '#EA580C')
  return {
    '--pv-primary': brand['600'],
    '--pv-primary-dark': brand['700'],
    '--pv-primary-light': brand['100'],
    '--pv-accent': form.theme_accent || '#F59E0B'
  }
})

const applyPreset = (p: { primary: string; accent: string }) => {
  form.theme_primary = p.primary
  form.theme_accent = p.accent
  saveTheme()
}

const presetChecked = (p: { primary: string }) => (form.theme_primary || '').toLowerCase() === p.primary.toLowerCase()

// translation
const testing = ref(false)
const testResult = ref<null | { ok: boolean; sample?: string; error?: string; provider?: string }>(null)
const runTest = async () => {
  testing.value = true
  testResult.value = await adminApi('/admin/translations/test', { method: 'POST' })
  testing.value = false
}

const runPending = async () => {
  const r = await adminApi<{ translated: number; failed: number }>('/admin/translations/run', { method: 'POST' })
  toast(`translated: ${r.translated ?? 0} / failed: ${r.failed ?? 0}`)
}

// password
const pw = reactive({ current: '', new: '' })
const changePassword = async () => {
  try {
    await adminApi('/auth/change-password', { method: 'POST', body: { current: pw.current, new: pw.new } })
    toast(t('admin.passwordChanged'))
    pw.current = pw.new = ''
  } catch (e: any) {
    toast(e?.data?.detail || t('admin.error'))
  }
}

useHead({ title: () => t('admin.settings') })
</script>

<template>
  <div>
    <h1 class="text-2xl font-extrabold text-ink-900 mb-6">{{ t('admin.settings') }}</h1>

    <div class="grid lg:grid-cols-2 gap-5 items-start">
      <!-- Theme management -->
      <div class="card p-6">
        <h3 class="font-extrabold text-ink-900 mb-1">{{ t('admin.theme') }}</h3>
        <p class="text-xs text-ink-400 mb-4">{{ t('admin.themeHint') }}</p>

        <div class="mb-4">
          <span class="label">{{ t('admin.themePresets') }}</span>
          <div class="grid grid-cols-2 sm:grid-cols-4 gap-2">
            <button
              v-for="p in THEME_PRESETS"
              :key="p.name"
              class="rounded-xl border-2 p-2.5 text-left transition hover:border-ink-300"
              :class="presetChecked(p) ? 'border-brand-600 bg-brand-50' : 'border-ink-200'"
              type="button"
              @click="applyPreset(p)"
            >
              <span class="flex gap-1 mb-1.5">
                <span class="w-4 h-4 rounded-full inline-block" :style="{ background: p.primary }" />
                <span class="w-4 h-4 rounded-full inline-block" :style="{ background: p.accent }" />
              </span>
              <span class="text-[11px] font-semibold text-ink-700">{{ p.name }}</span>
            </button>
          </div>
        </div>

        <div class="grid sm:grid-cols-2 gap-4 mb-4">
          <div>
            <span class="label">{{ t('admin.brandColor') }}</span>
            <div class="flex items-center gap-2">
              <input v-model="form.theme_primary" type="color" class="w-10 h-10 rounded-lg border border-ink-200 cursor-pointer bg-white p-1" aria-label="brand color" />
              <input v-model="form.theme_primary" class="input font-mono text-xs" />
            </div>
          </div>
          <div>
            <span class="label">{{ t('admin.accentColor') }}</span>
            <div class="flex items-center gap-2">
              <input v-model="form.theme_accent" type="color" class="w-10 h-10 rounded-lg border border-ink-200 cursor-pointer bg-white p-1" aria-label="accent color" />
              <input v-model="form.theme_accent" class="input font-mono text-xs" />
            </div>
          </div>
        </div>

        <div class="mb-4">
          <span class="label">{{ t('admin.cornerRadius') }} ({{ t('admin.radiusPx', { n: form.theme_radius }) }})</span>
          <input v-model.number="form.theme_radius" type="range" min="0" max="24" step="1" class="w-full accent-brand-600" />
        </div>

        <div class="flex items-center justify-between gap-3">
          <button class="btn-primary text-sm" @click="saveTheme">{{ t('admin.save') }}</button>
          <p class="text-[11px] text-ink-400 text-right max-w-[240px]">{{ t('admin.darkModeNote') }}</p>
        </div>
      </div>

      <!-- Live preview -->
      <div class="card p-6">
        <h3 class="font-extrabold text-ink-900 mb-4">{{ t('admin.themePreview') }}</h3>
        <div class="rounded-2xl border border-ink-100 p-5 bg-ink-50" :style="previewVars">
          <div class="bg-white rounded-xl p-4 shadow-sm">
            <div class="flex items-center gap-2 mb-3">
              <span class="w-8 h-8 rounded-lg text-white font-extrabold flex items-center justify-center" :style="{ background: 'var(--pv-primary)' }">{{ (form.site_name || 'S').charAt(0).toUpperCase() }}</span>
              <span class="font-extrabold text-ink-900">{{ form.site_name || 'Shopee' }}</span>
              <span class="ml-auto text-[10px] font-bold px-2 py-0.5 rounded-full" :style="{ background: 'var(--pv-primary-light)', color: 'var(--pv-primary-dark)' }">NEW</span>
            </div>
            <div class="h-20 rounded-lg mb-3 bg-ink-100 flex items-center justify-center text-ink-300 text-xs font-bold">IMAGE</div>
            <div class="text-sm font-semibold text-ink-800 mb-1">Pastel Phone Grip Stand</div>
            <div class="flex items-center justify-between">
              <span class="text-lg font-extrabold" :style="{ color: 'var(--pv-primary-dark)' }">₩12,400</span>
              <span class="text-white text-xs font-bold px-3 py-1.5 rounded-lg" :style="{ background: 'var(--pv-primary)' }">Cart</span>
            </div>
            <div class="mt-3 pt-3 border-t border-ink-100 flex items-center gap-1.5 text-xs text-ink-500">
              <span class="w-2 h-2 rounded-full inline-block" :style="{ background: 'var(--pv-accent)' }" />
              Free shipping over ₩50,000
            </div>
          </div>
        </div>
      </div>

      <!-- Typography management -->
      <div class="card p-6">
        <h3 class="font-extrabold text-ink-900 mb-1">{{ t('admin.typography') }}</h3>
        <p class="text-xs text-ink-400 mb-4">{{ t('admin.typographyHint') }}</p>
        <div class="grid sm:grid-cols-2 gap-4">
          <div>
            <span class="label">{{ t('admin.fontFamily') }}</span>
            <select v-model="form.fonts_family" class="input" :style="{ fontFamily: `'${form.fonts_family}', sans-serif` }">
              <option v-for="f in FONT_OPTIONS" :key="f.name" :value="f.name">{{ f.name }}</option>
            </select>
          </div>
          <div>
            <span class="label">{{ t('admin.headingFont') }}</span>
            <select v-model="form.fonts_heading" class="input" :style="{ fontFamily: `'${form.fonts_heading}', sans-serif` }">
              <option v-for="f in FONT_OPTIONS" :key="f.name" :value="f.name">{{ f.name }}</option>
            </select>
          </div>
          <div>
            <span class="label">{{ t('admin.baseSize') }}: {{ form.fonts_base_size }}px</span>
            <input v-model.number="form.fonts_base_size" type="range" min="14" max="18" step="1" class="w-full accent-brand-600" />
          </div>
          <div>
            <span class="label">{{ t('admin.headingWeight') }}</span>
            <select v-model.number="form.fonts_heading_weight" class="input">
              <option :value="600">600 (SemiBold)</option>
              <option :value="700">700 (Bold)</option>
              <option :value="800">800 (ExtraBold)</option>
              <option :value="900">900 (Black)</option>
            </select>
          </div>
        </div>
        <div class="mt-4 rounded-xl border border-ink-100 p-4 bg-ink-50">
          <div class="text-ink-900 text-xl font-extrabold" :style="{ fontFamily: `'${form.fonts_heading}', sans-serif`, fontWeight: form.fonts_heading_weight }">
            {{ form.fonts_heading }} headings
          </div>
          <div class="text-ink-600 text-sm mt-1" :style="{ fontFamily: `'${form.fonts_family}', sans-serif` }">
            {{ form.fonts_family }} body text. The quick brown fox jumps over the lazy dog. 한국어 미리보기 텍스트입니다.
          </div>
        </div>
        <button class="btn-primary text-sm mt-4" @click="saveFonts">{{ t('admin.save') }}</button>
      </div>

      <!-- Store settings -->
      <div class="card p-6">
        <h3 class="font-extrabold text-ink-900 mb-4">{{ t('admin.storeSettings') }}</h3>
        <div class="space-y-4">
          <div><span class="label">{{ t('admin.siteName') }}</span><input v-model="form.site_name" class="input" /></div>
          <div><span class="label">{{ t('admin.shippingFlat') }}</span><input v-model.number="form.shipping_flat" type="number" class="input" /></div>
          <div><span class="label">{{ t('admin.freeThreshold') }}</span><input v-model.number="form.free_shipping_threshold" type="number" class="input" /></div>
          <button class="btn-primary text-sm" @click="saveStore">{{ t('admin.save') }}</button>
        </div>
      </div>

      <!-- Downloads -->
      <div class="card p-6">
        <h3 class="font-extrabold text-ink-900 mb-1">{{ t('admin.downloads') }}</h3>
        <p class="text-xs text-ink-400 mb-4">{{ t('admin.downloadsHint') }}</p>
        <label class="flex items-center gap-3 cursor-pointer">
          <input v-model="form.download_zip_enabled" type="checkbox" class="w-4 h-4 accent-brand-600" />
          <span class="text-sm text-ink-700">{{ t('admin.zipEnabled') }}</span>
        </label>
        <button class="btn-primary text-sm mt-4" @click="saveSettings({ download_zip_enabled: !!form.download_zip_enabled })">{{ t('admin.save') }}</button>
      </div>

      <!-- Translation -->
      <div class="card p-6">
        <h3 class="font-extrabold text-ink-900 mb-1">{{ t('admin.translation') }}</h3>
        <p class="text-xs text-ink-400 mb-4">{{ t('admin.translateHint') }}</p>
        <div class="space-y-4">
          <div>
            <span class="label">{{ t('admin.provider') }}</span>
            <select v-model="form.translate_provider" class="input">
              <option value="google_free">{{ t('admin.providerFree') }}</option>
              <option value="edge">{{ t('admin.providerEdge') }}</option>
              <option value="gemini">Google Gemini (free key)</option>
              <option value="libre">LibreTranslate</option>
              <option value="papago">Papago (Naver)</option>
              <option value="deepl">DeepL</option>
              <option value="google">Google Cloud Translation</option>
              <option value="none">{{ t('admin.providerNone') }}</option>
            </select>
          </div>
          <div v-if="form.translate_provider === 'libre'">
            <span class="label">LibreTranslate URL</span>
            <input v-model="form.translate_libre_url" class="input" placeholder="https://your-libretranslate-server.com" />
          </div>
          <div v-if="!['none', 'google_free', 'edge'].includes(form.translate_provider)">
            <span class="label">{{ t('admin.apiKey') }}</span>
            <input v-model="form.translate_api_key" class="input" :placeholder="form.translate_provider === 'papago' ? 'X-NCP-APIGW-API-KEY-ID' : 'key'" />
          </div>
          <div v-if="form.translate_provider === 'papago'">
            <span class="label">{{ t('admin.apiSecret') }}</span>
            <input v-model="form.translate_api_secret" type="password" class="input" />
          </div>
          <div v-if="form.translate_provider === 'deepl'">
            <span class="label">{{ t('admin.deeplHost') }}</span>
            <select v-model="form.translate_deepl_host" class="input">
              <option value="free">Free (api-free.deepl.com)</option>
              <option value="pro">Pro (api.deepl.com)</option>
            </select>
          </div>
          <div class="flex flex-wrap gap-2">
            <button class="btn-primary text-sm" :disabled="form.translate_provider === 'none'" @click="saveSettings({ translate_provider: form.translate_provider, translate_api_key: form.translate_api_key, translate_api_secret: form.translate_api_secret, translate_deepl_host: form.translate_deepl_host, translate_libre_url: form.translate_libre_url })">{{ t('admin.save') }}</button>
            <button class="btn-secondary text-sm" :disabled="form.translate_provider === 'none' || testing" @click="runTest">{{ testing ? '…' : t('admin.testTranslation') }}</button>
            <button class="btn-secondary text-sm" :disabled="form.translate_provider === 'none'" @click="runPending">{{ t('admin.runPending') }}</button>
          </div>
          <p v-if="testResult" class="text-sm rounded-lg px-3 py-2" :class="testResult.ok ? 'bg-emerald-50 text-emerald-700 dark:bg-emerald-500/15 dark:text-emerald-300' : 'bg-rose-50 text-rose-700 dark:bg-rose-500/15 dark:text-rose-300'">
            {{ testResult.ok ? `OK (${testResult.provider}): "${testResult.sample}"` : testResult.error }}
          </p>
        </div>
      </div>

      <!-- Security -->
      <div class="card p-6">
        <h3 class="font-extrabold text-ink-900 mb-4">{{ t('admin.security') }}</h3>
        <form class="space-y-4 max-w-sm" @submit.prevent="changePassword">
          <div><span class="label">{{ t('admin.currentPassword') }}</span><input v-model="pw.current" type="password" class="input" autocomplete="current-password" /></div>
          <div><span class="label">{{ t('admin.newPassword') }}</span><input v-model="pw.new" type="password" class="input" autocomplete="new-password" /></div>
          <button class="btn-primary text-sm">{{ t('admin.changePassword') }}</button>
        </form>
      </div>
    </div>
  </div>
</template>
