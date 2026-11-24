<script setup lang="ts">
// Standalone auth screen: no admin shell/sidebar.
definePageMeta({ layout: false })
const { t } = useI18n()
const { siteName } = useTheme()
const api = useApi()
const route = useRoute()
const toast = useToastState()

const email = ref('admin@shopee.kr')
const password = ref('')
const busy = ref(false)
const error = ref('')

const submit = async () => {
  busy.value = true
  error.value = ''
  try {
    const res = await api<{ access_token: string }>('/auth/login', {
      method: 'POST',
      body: { email: email.value, password: password.value }
    })
    useCookie<string | null>('shopee_admin_token').value = res.access_token
    const to = String(route.query.redirect || '')
    navigateTo(to.startsWith('/') && !to.startsWith('//') ? to : '/admin')
  } catch {
    error.value = t('admin.loginError')
  } finally {
    busy.value = false
  }
}

useHead({ title: () => t('admin.login') })
</script>

<template>
  <div class="min-h-screen flex items-center justify-center p-4 bg-ink-50">
    <div class="card w-full max-w-sm p-8">
      <div class="text-center mb-6">
        <span class="w-12 h-12 rounded-2xl bg-brand-600 text-white text-2xl font-extrabold inline-flex items-center justify-center shadow-pop mb-3">{{ (siteName || 'S').charAt(0).toUpperCase() }}</span>
        <h1 class="text-xl font-extrabold text-ink-900">{{ t('admin.login') }}</h1>
      </div>
      <form class="space-y-4" @submit.prevent="submit">
        <div>
          <label class="label" for="login-email">{{ t('admin.email') }}</label>
          <input id="login-email" v-model="email" type="email" class="input" required autocomplete="username" />
        </div>
        <div>
          <label class="label" for="login-password">{{ t('admin.password') }}</label>
          <input id="login-password" v-model="password" type="password" class="input" required autocomplete="current-password" />
        </div>
        <p v-if="error" class="text-sm text-rose-600 font-semibold">{{ error }}</p>
        <button class="btn-primary w-full !py-3" :disabled="busy">{{ busy ? t('admin.signingIn') : t('admin.signIn') }}</button>
      </form>
    </div>
  </div>
</template>
