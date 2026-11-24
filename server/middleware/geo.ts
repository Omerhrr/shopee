/**
 * Korea geo-locale rule: visitors from Korea get Korean on their next page view.
 * Uses standard CDN geo headers (cf-ipcountry / x-vercel-ip-country / x-country).
 * Manual locale switching (header switcher) always wins via cookie.
 */
export default defineEventHandler((event) => {
  const existing = getCookie(event, 'locale')
  if (existing) return
  const country =
    getHeader(event, 'cf-ipcountry') ||
    getHeader(event, 'x-vercel-ip-country') ||
    getHeader(event, 'x-country') ||
    ''
  if (country.toUpperCase() === 'KR') {
    setCookie(event, 'locale', 'ko', { path: '/', maxAge: 60 * 60 * 24 * 365, sameSite: 'lax' })
  }
})
