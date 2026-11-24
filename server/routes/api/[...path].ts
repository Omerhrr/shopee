/**
 * Proxy /api/** to the FastAPI mini-service (port 8000).
 * event.path already includes the /api prefix - forward as-is.
 */
import { proxyRequest } from 'h3'

export default defineEventHandler(async (event) => {
  const config = useRuntimeConfig(event)
  const target = (config.apiInternal || 'http://127.0.0.1:8000') + event.path
  return proxyRequest(event, target)
})
