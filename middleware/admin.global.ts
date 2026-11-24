/**
 * Guard /admin/** routes.
 * - No token -> redirect to /admin/login
 * - Token present -> validated against the API (/auth/me); stale or forged
 *   tokens are cleared so the visitor lands on a clean login screen instead
 *   of a dashboard full of 401 errors.
 * - Logged-in visitors on /admin/login are sent back to /admin.
 * - If the API itself is unreachable we fail open (never lock the user out).
 */
export default defineNuxtRouteMiddleware(async (to) => {
  // /scraper exposes wholesale cost + supplier data, so it needs the admin session too
  if (!to.path.startsWith('/admin') && to.path !== '/scraper') return

  const token = useCookie<string | null>('shopee_admin_token')

  if (to.path === '/admin/login') {
    if (!token.value) return
    if (await tokenValid(token.value)) return navigateTo('/admin')
    token.value = null
    return
  }

  const loginUrl = to.path === '/scraper' ? '/admin/login?redirect=/scraper' : '/admin/login'
  if (!token.value) return navigateTo(loginUrl)
  if (!(await tokenValid(token.value))) {
    token.value = null
    return navigateTo(loginUrl)
  }
})

async function tokenValid(token: string | null): Promise<boolean> {
  if (!token) return false
  try {
    const config = useRuntimeConfig()
    const base = import.meta.server
      ? (config.apiInternal || 'http://127.0.0.1:8000') + '/api'
      : '/api'
    await $fetch(base + '/auth/me', { headers: { Authorization: `Bearer ${token}` } })
    return true
  } catch (e: any) {
    const status = e?.response?.status || e?.status
    // Only a hard 401 invalidates the session; network errors fail open.
    return status !== 401
  }
}
