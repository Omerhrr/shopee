"""Shopee API - FastAPI + SQLAlchemy backend for the Korean dropshipping storefront."""
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from . import models  # noqa: F401 (loads models for table creation)
from .config import MEDIA_DIR
from .database import Base, SessionLocal, engine
from .routers import admin_catalog, admin_finance, admin_settings, admin_sources, auth, catalog, orders
from .services.scheduler import start_scheduler
from .services.seed_service import ensure_seed


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        ensure_seed(db)  # idempotent: settings, admin user, categories, 114 sources, demo catalog
    finally:
        db.close()
    start_scheduler()
    yield


app = FastAPI(title="Shopee Dropshipping API", version="1.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
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

# Scraped images / generated placeholders
app.mount("/media", StaticFiles(directory=str(MEDIA_DIR)), name="media")


@app.get("/api/health")
def health():
    return {"ok": True, "service": "shopee-api"}
