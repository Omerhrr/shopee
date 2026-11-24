/**
 * Browser-language detection (client only, after mount to avoid hydration mismatch).
 * Korean browsers get Korean UI; everyone else English. Cookie wins.
 */
export default defineNuxtPlugin((nuxtApp) => {
  nuxtApp.hook('app:mounted', () => {
    const cookie = useCookie<string | null>('locale')
    if (cookie.value) return
    const lang = (navigator.language || '').toLowerCase()
    if (lang.startsWith('ko')) {
      const locale = useState<string>('locale')
      locale.value = 'ko'
      cookie.value = 'ko'
      document.documentElement.lang = 'ko'
    }
  })
})
