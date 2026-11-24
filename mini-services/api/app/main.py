"""Shopee API - FastAPI + SQLAlchemy backend for the Korean dropshipping storefront."""
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi import HTTPException
from fastapi.responses import Response

from . import models  # noqa: F401 (loads models for table creation)
from .config import IS_VERCEL
from .services import media_store
from .database import Base, SessionLocal, engine
from .routers import admin_catalog, admin_export, admin_finance, admin_settings, admin_sources, auth, catalog, cron, orders, scraper
from .services.scheduler import start_scheduler
from .services.seed_service import ensure_seed


_initialised = False


def init_app():
    """Create tables + idempotent seed (settings, admin, categories, sources)."""
    global _initialised
    if _initialised:
        return
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        ensure_seed(db)
    finally:
        db.close()
    _initialised = True


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_app()
    if not IS_VERCEL:  # serverless: Vercel Cron calls /api/cron/run instead
        start_scheduler()
    yield


if IS_VERCEL:
    # Serverless runtimes may not run the ASGI lifespan: initialise on cold start.
    init_app()


app = FastAPI(title="Shopee Dropshipping API", version="1.0.0", lifespan=lifespan)

import os

_origins = [o.strip() for o in os.getenv("SHOPEE_CORS_ORIGINS", "*").split(",") if o.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_origins,
    allow_credentials=False,  # auth uses a Bearer header, not cookies
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(catalog.router)
app.include_router(orders.router)
app.include_router(auth.router)
app.include_router(admin_catalog.router)
app.include_router(admin_sources.router)
app.include_router(admin_settings.router)
app.include_router(admin_finance.router)
app.include_router(admin_export.router)
app.include_router(scraper.router)
app.include_router(cron.router)

# Scraped images / generated placeholders
class _PathNormalizer:
    """Vercel may deliver the rewrite target (/api/index) or a path without the /api prefix.
    All our routes live under /api/* or /media/*, so normalise before routing."""

    def __init__(self, inner):
        self.inner = inner

    async def __call__(self, scope, receive, send):
        if scope["type"] in ("http", "websocket"):
            path = scope.get("path") or "/"
            if path in ("/", "") or path.startswith("/api/index"):
                # rewrite lost the browser path: recover it from proxy headers when present
                hd = {k.decode().lower(): v.decode() for k, v in scope.get("headers", [])}
                for key in ("x-vercel-original-path", "x-original-uri", "x-forwarded-uri", "x-matched-path"):
                    cand = hd.get(key, "")
                    if cand.startswith("/") and "[" not in cand and not cand.startswith("/api/index"):
                        path = cand.split("?")[0]
                        break
            if path.startswith("/api/index"):
                path = path[len("/api/index"):] or "/"
            if not (path.startswith("/api/") or path == "/api" or path.startswith("/media/")):
                path = "/api" + (path if path.startswith("/") else "/" + path)
            scope = dict(scope, path=path, raw_path=path.encode())
        await self.inner(scope, receive, send)


if IS_VERCEL:
    app.add_middleware(_PathNormalizer)


@app.get("/media/{path:path}")
def media(path: str):
    hit = media_store.load(path)
    if not hit:
        raise HTTPException(404, "Not found")
    data, ctype = hit
    return Response(data, media_type=ctype, headers={"Cache-Control": "public, max-age=86400"})


@app.get("/api/health")
def health():
    return {"ok": True, "service": "shopee-api"}
