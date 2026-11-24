"""Admin: app settings + translation pipeline control."""
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from .. import models
from ..database import get_db
from ..deps import get_current_admin, get_setting, set_setting
from ..services.scheduler import reschedule_scrape
from ..services.translator import pending_count, run_pending_translations, test_provider

router = APIRouter(prefix="/api/admin", tags=["admin-settings"], dependencies=[Depends(get_current_admin)])

EDITABLE_KEYS = {
    "site_name", "currency", "default_locale", "markup_percent", "shipping_flat",
    "free_shipping_threshold", "scrape_enabled", "scrape_interval_minutes",
    "scrape_max_products_per_run", "translate_provider", "translate_api_key",
    "translate_api_secret", "translate_deepl_host",
    "theme_primary", "theme_accent", "theme_radius", "theme_dark_default",
    "fonts_family", "fonts_heading", "fonts_base_size", "fonts_heading_weight",
}


@router.get("/settings")
def get_settings(db: Session = Depends(get_db)):
    rows = db.query(models.Setting).all()
    return {r.key: r.value for r in rows}


@router.put("/settings")
def put_settings(body: dict, db: Session = Depends(get_db)):
    changed_scrape = False
    for key, value in body.items():
        if key not in EDITABLE_KEYS:
            continue
        if key.startswith("scrape_"):
            changed_scrape = True
        set_setting(db, key, value)
    db.commit()
    if changed_scrape:
        reschedule_scrape()
    rows = db.query(models.Setting).all()
    return {r.key: r.value for r in rows}


@router.get("/translations/pending")
def translations_pending(db: Session = Depends(get_db)):
    items = (
        db.query(models.Product)
        .filter(models.Product.translation_status == "pending", models.Product.original_lang == "ko")
        .limit(20)
        .all()
    )
    return {
        "count": pending_count(db),
        "provider": get_setting(db, "translate_provider", "none"),
        "items": [{"id": p.id, "title_ko": p.title_ko, "slug": p.slug} for p in items],
    }


@router.post("/translations/run")
def translations_run(db: Session = Depends(get_db)):
    return run_pending_translations(db, limit=40)


@router.post("/translations/test")
def translations_test(db: Session = Depends(get_db)):
    return test_provider(db)
