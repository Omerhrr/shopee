/**
 * Sync locale state with the cookie on both server (SSR) and client (hydration)
 * so the rendered language is always deterministic, and keep <html lang>
 * in sync reactively (accessibility + SEO).
 */
export default defineNuxtPlugin(() => {
  const cookie = useCookie<string | null>('locale')
  const locale = useState<string>('locale', () => 'en')
  if (cookie.value === 'ko' || cookie.value === 'en') {
    locale.value = cookie.value
  }
  useHead(() => ({ htmlAttrs: { lang: locale.value } }))
})
