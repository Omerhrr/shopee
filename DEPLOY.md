# Deploying on Vercel (two projects, one repo)

Vercel's filesystem is read-only (except /tmp) and there is no always-on process, so the backend
runs in "serverless mode" automatically (detected via the `VERCEL` env var):
- database: Postgres (Neon / Vercel Postgres / Supabase), NOT SQLite
- images: stored in the database (table `media_files`), served from `/media/...`
- scheduler: replaced by Vercel Cron (`/api/cron/run`, daily 03:00 UTC; Hobby plan allows daily only)

## 1. API project  (Root Directory: `mini-services/api`)
Vercel detects `api/index.py` + `vercel.json` (all paths rewritten to the FastAPI app).
Environment variables:
| name | value |
|---|---|
| `DATABASE_URL` (or `SHOPEE_DATABASE_URL`) | Postgres connection string (use the pooled one) |
| `SHOPEE_SECRET_KEY` | long random string (required) |
| `SHOPEE_ADMIN_EMAIL` / `SHOPEE_ADMIN_PASSWORD` | first admin account, change the defaults |
| `CRON_SECRET` | random string; Vercel sends it to the cron route as a Bearer token |
| `SHOPEE_CORS_ORIGINS` | your site URL, e.g. `https://your-site.vercel.app` |
Tables and seed data are created on the first cold start. Check `GET /api/health`.

Limits to know: functions stop at 300 s, so scrape runs are time-boxed (240 s) and rotate through the
least-recently-scraped sources. Large image ZIP exports build in memory.

## 2. Site project  (Root Directory: repo root)
| name | value |
|---|---|
| `NUXT_API_INTERNAL` | `https://<api-project>.vercel.app` (no trailing slash, no /api) |
| `NUXT_PUBLIC_API_BASE` | `https://<api-project>.vercel.app/api` (browser calls the API directly: avoids the 4.5 MB proxy limit on ZIP downloads) |

`/` redirects to `/scraper` (admin login required). Storefront stays at `/products`.

## Local development
Unchanged: `bun run dev` (starts the API automatically, SQLite + images on disk).
Other hosts with a persistent disk can use `mini-services/api/Dockerfile` instead.
