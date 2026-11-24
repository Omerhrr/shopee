/**
 * API supervisor (Nitro plugin):
 * FastAPI runs as a separate mini-service on :8000. The platform only starts
 * it during the boot sequence, so if it dies mid-session nothing would bring
 * it back. This plugin (running inside the long-lived Nuxt dev process)
 * health-checks the API and respawns it whenever it is unreachable.
 */
import { spawn } from 'node:child_process'
import { join } from 'node:path'

let spawning = false

function healthy() {
  return $fetch('http://127.0.0.1:8000/api/health', { timeout: 1500 })
    .then((res) => !!(res && res.ok))
    .catch(() => false)
}

function startApi() {
  if (spawning) return
  spawning = true
  try {
    const root = process.cwd()
    const child = spawn('bash', [join(root, 'mini-services/api/start.sh')], {
      stdio: 'ignore',
      detached: false,
      cwd: root,
      env: process.env
    })
    child.on('error', () => {
      spawning = false
    })
    child.on('exit', () => {
      spawning = false
    })
    child.unref()
  } catch {
    spawning = false
  }
  // avoid spawning in a tight loop
  setTimeout(() => {
    spawning = false
  }, 15000)
}

export default function () {
  healthy().then((ok) => {
    if (!ok) startApi()
  })
  setInterval(() => {
    healthy().then((ok) => {
      if (!ok) startApi()
    })
  }, 60000)
}
