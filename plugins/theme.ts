/**
 * Theme bootstrap (universal):
 * - loads theme + typography settings from the API (SSR-cached via payload)
 * - injects the CSS variables block and Google Fonts stylesheet into <head>
 *   so the very first server render already carries the admin-selected theme
 * - keeps <html data-mode> in sync for dark mode
 * - installs a tiny pre-hydration click guard so the dark-mode button still
 *   works if the visitor clicks before Vue has mounted (slow network / dev
 *   cold start): it flips <html data-mode> + cookie, and Vue picks the cookie
 *   up when the app initializes.
 */

const PRE_HYDRATION_MODE_SCRIPT = `
(function () {
  if (window.__modeGuard) return
  window.__modeGuard = true
  document.addEventListener('click', function (e) {
    if (window.__appMounted) return
    var t = e.target && e.target.closest ? e.target.closest('[data-mode-toggle]') : null
    if (!t) return
    var html = document.documentElement
    var next = html.getAttribute('data-mode') === 'dark' ? 'light' : 'dark'
    html.setAttribute('data-mode', next)
    document.cookie = 'shopee_mode=' + next + '; path=/; max-age=31536000; SameSite=Lax'
    if (e.cancelable) e.preventDefault()
    e.stopPropagation()
  }, true)
})()
`

export default defineNuxtPlugin(async (nuxtApp) => {
  const { settings, mode, varsCss, fontsHref } = await loadThemeSettings()

  nuxtApp.hook('app:mounted', () => {
    (window as unknown as { __appMounted?: boolean }).__appMounted = true
  })

  nuxtApp.runWithContext(() => {
    useHead(() => ({
      style: [{ innerHTML: varsCss.value, key: 'shopee-theme-vars' }],
      link: fontsHref.value ? [{ rel: 'stylesheet', href: fontsHref.value, id: 'shopee-theme-fonts' }] : [],
      htmlAttrs: { 'data-mode': mode.value }
    }))
    // Base font size scale (typography management)
    useHead(() => ({
      style: [{ innerHTML: `html{font-size:${settings.value.fonts.baseSize || 16}px}`, key: 'shopee-base-size' }]
    }))
    // Pre-hydration dark-mode toggle guard (see comment above)
    useHead({
      script: [{ innerHTML: PRE_HYDRATION_MODE_SCRIPT, tagPosition: 'head' }]
    })
  })
})
