/** Stream /media/** (product images) from the FastAPI static dir. */
import { proxyRequest } from 'h3'

export default defineEventHandler(async (event) => {
  const config = useRuntimeConfig(event)
  const target = (config.apiInternal || 'http://127.0.0.1:8000') + event.path
  return proxyRequest(event, target)
})
