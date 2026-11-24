/**
 * API bridge.
 * - Browser: relative /api/** (Nitro proxies to the FastAPI mini-service on :8000)
 * - SSR: direct internal call to FastAPI
 * Same for /media images (Nitro route streams them).
 */
export function useApi() {
  const config = useRuntimeConfig()
  const internal = import.meta.server ? (config.apiInternal || 'http://127.0.0.1:8000') : ''
  return function api<T = any>(path: string, opts: any = {}): Promise<T> {
    const url = import.meta.server ? internal + '/api' + path : '/api' + path
    return $fetch<T>(url, opts) as Promise<T>
  }
}

/** Admin API client: attaches Bearer token from cookie and self-heals stale sessions. */
export function useAdminApi() {
  const api = useApi()
  return async function adminApi<T = any>(path: string, opts: any = {}): Promise<T> {
    const token = useCookie<string | null>('shopee_admin_token')
    const headers: Record<string, string> = { ...(opts.headers || {}) }
    if (token.value) headers.Authorization = `Bearer ${token.value}`
    try {
      return await api<T>(path, { ...opts, headers })
    } catch (e: any) {
      const status = e?.response?.status || e?.status
      // Expired/invalid token: clear it and drop the user on the login screen
      // instead of leaving them on a dashboard full of 401 errors.
      if (status === 401 && token.value && path !== '/auth/login') {
        token.value = null
        if (import.meta.client) window.location.href = '/admin/login'
      }
      throw e
    }
  }
}
