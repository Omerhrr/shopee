# Deploying

Vercel hosts the Nuxt site only. The FastAPI backend (SQLite DB, scraper, scheduler,
downloaded images) needs a host with a persistent disk (Render, Railway, Fly.io, a VPS).
Vercel serverless has no writable persistent storage and cannot run the background scheduler.

## 1. Backend (mini-services/api)
Use the included `Dockerfile`; mount persistent disks at `/app/data` and `/app/media`.
Environment variables:
- `SHOPEE_SECRET_KEY`  long random string (required for stable admin sessions)
- `SHOPEE_ADMIN_EMAIL` / `SHOPEE_ADMIN_PASSWORD`  first admin account (change the defaults!)
- `SHOPEE_CORS_ORIGINS`  e.g. `https://your-site.vercel.app` (only needed for direct browser calls)
Health check: `GET /api/health`.

## 2. Vercel
Import the repo (framework: Nuxt, bun detected). Environment variables:
- `NUXT_API_INTERNAL` = `https://your-backend-host`   (no trailing slash, no /api)
- `NUXT_PUBLIC_API_BASE` = `https://your-backend-host/api`   (optional, recommended: big
  ZIP downloads then bypass Vercel's ~4.5 MB function response limit; also set CORS above)

## 3. Routes
`/` redirects to `/scraper` (admin login required). Storefront is still at `/products`.
