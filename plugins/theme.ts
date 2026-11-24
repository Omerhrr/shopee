/**
 * Theme bootstrap (universal):
 * - loads theme + typography settings from the API (SSR-cached via payload)
 * - injects the CSS variables block and Google Fonts stylesheet into <head>
 *   so the very first server render already carries the admin-selected theme
 * - keeps <html data-mode> in sync for dark mode
 */
export default defineNuxtPlugin(async (nuxtApp) => {
  const { settings, mode, varsCss, fontsHref } = await loadThemeSettings()

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
  })
})
