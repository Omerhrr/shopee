"""Application configuration - paths, defaults, secrets."""
import os
import secrets
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent  # mini-services/api
APP_DIR = BASE_DIR / "app"
DATA_DIR = BASE_DIR / "data"
MEDIA_DIR = BASE_DIR / "media"
SEED_DIR = BASE_DIR / "seed"
SCRAPED_DIR = MEDIA_DIR / "scraped"

DATA_DIR.mkdir(exist_ok=True)
MEDIA_DIR.mkdir(exist_ok=True)

DB_PATH = DATA_DIR / "shopee.db"
DATABASE_URL = os.getenv("SHOPEE_DATABASE_URL", f"sqlite:///{DB_PATH}")

# Demo-grade secret; override with SHOPEE_SECRET_KEY in production.
# When no env key is set, a random secret is generated ONCE and persisted to
# data/secret.key so admin login sessions survive backend restarts.
def _load_secret() -> str:
    env = os.getenv("SHOPEE_SECRET_KEY")
    if env:
        return env
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
    "scrape_interval_minutes": 360,
    "scrape_max_products_per_run": 10,
    # Auto translation of scraped Korean listings
    "translate_provider": "google_free",  # google_free | papago | deepl | google | none
    "translate_api_key": "",
    "translate_api_secret": "",  # Papago client secret
    "translate_deepl_host": "free",  # free | pro
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
