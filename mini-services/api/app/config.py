"""Application configuration - paths, defaults, secrets."""
import os
import secrets
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent  # mini-services/api
APP_DIR = BASE_DIR / "app"
# Vercel: read-only filesystem except /tmp (not shared between instances) -> serverless mode.
IS_VERCEL = bool(os.getenv("VERCEL"))
_WRITABLE = Path("/tmp/shopee") if IS_VERCEL else BASE_DIR
DATA_DIR = _WRITABLE / "data"
MEDIA_DIR = _WRITABLE / "media"
# Images live in the database (table media_files) on Vercel, on disk elsewhere.
MEDIA_IN_DB = IS_VERCEL or os.getenv("SHOPEE_MEDIA_STORE", "").lower() == "db"
SEED_DIR = BASE_DIR / "seed"
SCRAPED_DIR = MEDIA_DIR / "scraped"

DATA_DIR.mkdir(parents=True, exist_ok=True)
MEDIA_DIR.mkdir(parents=True, exist_ok=True)

DB_PATH = DATA_DIR / "shopee.db"
def _normalize_db_url(url: str) -> str:
    # Neon / Vercel Postgres hand out postgres:// or postgresql:// URLs; use the psycopg 3 driver.
    if url.startswith("postgres://"):
        url = "postgresql://" + url[len("postgres://"):]
    if url.startswith("postgresql://"):
        url = "postgresql+psycopg://" + url[len("postgresql://"):]
    return url


DATABASE_URL = _normalize_db_url(
    os.getenv("SHOPEE_DATABASE_URL") or os.getenv("DATABASE_URL") or os.getenv("POSTGRES_URL") or f"sqlite:///{DB_PATH}"
)
CRON_SECRET = os.getenv("CRON_SECRET", "")

# Demo-grade secret; override with SHOPEE_SECRET_KEY in production.
# When no env key is set, a random secret is generated ONCE and persisted to
# data/secret.key so admin login sessions survive backend restarts.
def _load_secret() -> str:
    env = os.getenv("SHOPEE_SECRET_KEY")
    if env:
        return env
    if IS_VERCEL:
        raise RuntimeError("Set SHOPEE_SECRET_KEY in the Vercel project environment variables")
    key_file = DATA_DIR / "secret.key"
    if key_file.exists():
        return key_file.read_text(encoding="utf-8").strip()
    key = "dev-" + secrets.token_hex(16)
    key_file.write_text(key, encoding="utf-8")
    return key


SECRET_KEY = _load_secret()
TOKEN_ALGORITHM = "HS256"
TOKEN_EXPIRE_MINUTES = 60 * 24 * 7  # 7 days

SEED_ADMIN_EMAIL = os.getenv("SHOPEE_ADMIN_EMAIL", "admin@shopee.kr")
SEED_ADMIN_PASSWORD = os.getenv("SHOPEE_ADMIN_PASSWORD", "admin1234")

DEFAULT_SETTINGS = {
    "site_name": "Shopee",
    "currency": "KRW",
    "default_locale": "en",
    # Business rule: markup applied on top of every scraped wholesale price
    "markup_percent": 35.0,
    "shipping_flat": 2500,
    "free_shipping_threshold": 50000,
    # Scraping / auto-update of new listings
    "scrape_enabled": True,
    "download_zip_enabled": True,
    "scrape_interval_minutes": 360,
    "scrape_max_products_per_run": 500,
    # Auto translation of scraped Korean listings
    "translate_provider": "google_free",  # google_free | papago | deepl | google | none
    "translate_api_key": "",
    "translate_api_secret": "",  # Papago client secret
    "translate_deepl_host": "free",  # free | pro
    "translate_libre_url": "",        # LibreTranslate server, e.g. https://libretranslate.example.com
    # Theme management (Admin > Settings > Theme)
    "theme_primary": "#EA580C",   # brand color, full palette is derived from it
    "theme_accent": "#F59E0B",    # highlight color (topbar, hero, bullets)
    "theme_radius": 12,            # base corner radius in px
    "theme_dark_default": False,   # storefront starts in light mode (visitor can toggle)
    # Typography management (Admin > Settings > Typography)
    "fonts_family": "Inter",       # body font family
    "fonts_heading": "Inter",      # heading font family
    "fonts_base_size": 16,         # base font size in px
    "fonts_heading_weight": 800,   # heading weight (400-900)
}
