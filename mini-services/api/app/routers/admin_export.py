"""Admin: export the catalog to Shopee Korea Seller Center (KRSC).

Two supported routes:
1. Mass-upload CSV + image ZIP  -> Seller Center (seller.shopee.kr) bulk upload.
2. Shopee Open Platform API     -> automated push (needs the seller's own app credentials,
   registered at open.shopee.com; KRSC guide lists the exact partner host).

This router implements route 1 fully (no credentials needed) and keeps the row
builder shared so route 2 can reuse it once credentials exist.
"""
import csv
import io
import os
import tempfile
import zipfile
from datetime import datetime

from fastapi import APIRouter, Depends
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel
from sqlalchemy import func, or_
from sqlalchemy.orm import Session, joinedload
from starlette.background import BackgroundTask

from .. import models
from ..services import media_store
from ..services.translator import ensure_translated
from ..database import get_db
from ..deps import get_current_admin

router = APIRouter(prefix="/api/admin/export", tags=["admin-export"], dependencies=[Depends(get_current_admin)])

TITLE_MAX = 255          # Shopee item name limit
DESC_MAX = 3000
MAX_IMAGES = 5           # image URL columns in the mass-upload CSV
MAX_ZIP_FILES = 3000
ALLOWED_IMG_EXT = {".jpg", ".jpeg", ".png", ".webp"}


class ExportParams(BaseModel):
    """Shared query parameters for preview / csv / zip endpoints."""
    q: str = ""
    category_id: int | None = None
    source_id: int | None = None
    title_lang: str = "en"            # en (fallback ko) | ko (fallback en)
    currency: str = "KRW"             # KRW | USD (KRSC cross-border often prices in USD)
    usd_rate: float = 1350.0          # KRW per 1 USD
    stock: int = 10
    weight_g: int = 500
    length_cm: float = 25
    width_cm: float = 20
    height_cm: float = 10
    public_base: str = "http://localhost:3000"  # where /media is publicly reachable


def _filter_query(db: Session, p: ExportParams):
    """Published products from enabled sources, with the same filters as the admin UI."""
    query = (
        db.query(models.Product)
        .options(joinedload(models.Product.category), joinedload(models.Product.source))
        .outerjoin(models.Source, models.Product.source_id == models.Source.id)
        .filter(
            models.Product.status == "published",
            or_(models.Product.source_id.is_(None), models.Source.enabled.is_(True)),
        )
    )
    if p.q:
        like = f"%{p.q}%"
        query = query.filter(
            or_(
                models.Product.title_ko.ilike(like),
                models.Product.title_en.ilike(like),
                models.Product.slug.ilike(like),
            )
        )
    if p.category_id:
        query = query.filter(models.Product.category_id == p.category_id)
    if p.source_id:
        query = query.filter(models.Product.source_id == p.source_id)
    return query.order_by(models.Product.id)


def _title(prod: models.Product, lang: str) -> str:
    if lang == "en":
        t = (prod.title_en or "").strip() or (prod.title_ko or "").strip()
    else:
        t = (prod.title_ko or "").strip() or (prod.title_en or "").strip()
    return " ".join(t.split())[:TITLE_MAX]


def _desc(prod: models.Product, lang: str, title: str) -> str:
    d = ""
    if lang == "en":
        d = (prod.desc_en or "").strip() or (prod.desc_ko or "").strip()
    else:
        d = (prod.desc_ko or "").strip() or (prod.desc_en or "").strip()
    d = " ".join(d.split())
    if len(d) < 20:
        d = f"{title}. New item sourced from a verified Korean wholesaler. Ships from Korea with tracking."
    return d[:DESC_MAX]


def _price(prod: models.Product, p: ExportParams):
    v = prod.price_sell or 0
    if p.currency.upper() == "USD" and p.usd_rate > 0:
        return round(v / p.usd_rate, 2)
    return v


def _image_urls(prod: models.Product, base: str) -> list[str]:
    urls: list[str] = []
    for img in (prod.images or []):
        if not isinstance(img, str) or not img.strip():
            continue
        u = img.strip()
        if u.startswith(("http://", "https://")):
            urls.append(u)
        else:
            urls.append(base.rstrip("/") + "/" + u.lstrip("/"))
        if len(urls) >= MAX_IMAGES:
            break
    return urls


def _needs_translation(prod: models.Product, lang: str) -> bool:
    return lang == "en" and not (prod.title_en or "").strip()


def _local_image(prod: models.Product) -> tuple[bytes, str] | None:
    """First stored image (under /media) with a Shopee-friendly extension -> (bytes, ext)."""
    for img in (prod.images or []):
        if not isinstance(img, str):
            continue
        u = img.strip()
        if not u or u.startswith(("http://", "https://")):
            continue
        ext = os.path.splitext(u)[1].lower()
        if ext not in ALLOWED_IMG_EXT:
            continue
        hit = media_store.load(u)
        if hit and len(hit[0]) > 512:
            return hit[0], ".jpg" if ext == ".jpeg" else ext
    return None


def build_rows(db: Session, p: ExportParams, translate: bool = True) -> list[dict]:
    prods = _filter_query(db, p).all()
    if translate:
        try:  # translate missing titles/descriptions into the chosen export language first
            ensure_translated(db, prods, p.title_lang, budget_s=50, max_items=400)
        except Exception:
            db.rollback()
    rows = []
    for prod in prods:
        urls = _image_urls(prod, p.public_base)
        price = _price(prod, p)
        if not urls or price <= 0:
            continue  # Shopee requires at least 1 image and a positive price
        sku = f"SP-{prod.id:06d}"
        title = _title(prod, p.title_lang)
        cat = prod.category
        rows.append(
            {
                "sku": sku,
                "title": title,
                "desc": _desc(prod, p.title_lang, title),
                "price": price,
                "stock": max(1, int(p.stock)),
                "images": urls,
                "needs_translation": _needs_translation(prod, p.title_lang),
                "category_en": cat.name_en if cat else "",
                "category_ko": cat.name_ko if cat else "",
                "source": prod.source.name if prod.source else "",
                "source_url": prod.source_url or "",
            }
        )
    return rows


CSV_HEADERS = [
    "Category ID", "Product Name", "Description", "Price", "Stock", "Item SKU", "Logistics",
    *(f"Product Image URL {i}" for i in range(1, MAX_IMAGES + 1)),
    "Weight (g)", "Package Length (cm)", "Package Width (cm)", "Package Height (cm)",
    "Source Product URL",  # original supplier page of the exact product (extra column, last)
]


def _to_csv_bytes(rows: list[dict], p: ExportParams) -> bytes:
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(CSV_HEADERS)
    for r in rows:
        imgs = list(r["images"]) + [""] * (MAX_IMAGES - len(r["images"]))
        w.writerow(
            [
                "",  # Category ID: filled from Seller Center's category list
                r["title"],
                r["desc"],
                r["price"],
                r["stock"],
                r["sku"],
                "",  # Logistics: left to Seller Center defaults
                *imgs,
                p.weight_g,
                p.length_cm,
                p.width_cm,
                p.height_cm,
                r["source_url"],
            ]
        )
    return b"\xef\xbb\xbf" + buf.getvalue().encode("utf-8")  # BOM so Excel opens Korean text correctly


@router.get("/shopee/preview")
def preview(p: ExportParams = Depends(), db: Session = Depends(get_db)):
    all_prods = _filter_query(db, p).all()
    total = len(all_prods)
    needs_translation = sum(1 for prod in all_prods if _needs_translation(prod, p.title_lang))
    no_image = sum(1 for prod in all_prods if not _image_urls(prod, p.public_base))
    no_price = sum(1 for prod in all_prods if (prod.price_sell or 0) <= 0)

    cat_counts = (
        db.query(models.Category.name_en, models.Category.name_ko, func.count(models.Product.id))
        .join(models.Product, models.Product.category_id == models.Category.id)
        .outerjoin(models.Source, models.Product.source_id == models.Source.id)
        .filter(
            models.Product.status == "published",
            or_(models.Product.source_id.is_(None), models.Source.enabled.is_(True)),
        )
        .group_by(models.Category.id)
        .order_by(func.count(models.Product.id).desc())
        .all()
    )

    rows = build_rows(db, p, translate=False)
    return {
        "total": total,
        "exportable": len(rows),
        "needs_translation": needs_translation,
        "no_image": no_image,
        "no_price": no_price,
        "by_category": [{"name_en": a, "name_ko": b, "n": c} for a, b, c in cat_counts[:20]],
        "samples": [
            {
                "sku": r["sku"],
                "title": r["title"],
                "price": r["price"],
                "currency": p.currency.upper(),
                "category_en": r["category_en"],
                "images": len(r["images"]),
            }
            for r in rows[:5]
        ],
    }


@router.get("/shopee.csv")
def export_csv(p: ExportParams = Depends(), db: Session = Depends(get_db)):
    rows = build_rows(db, p)
    data = _to_csv_bytes(rows, p)
    stamp = datetime.now().strftime("%Y%m%d")
    return Response(
        content=data,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="shopee_mass_upload_{stamp}.csv"'},
    )


@router.get("/shopee-images.zip")
def export_images_zip(p: ExportParams = Depends(), db: Session = Depends(get_db)):
    """Product images named by Item SKU so they can be matched to CSV rows in Seller Center."""
    prods = _filter_query(db, p).all()
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".zip")
    tmp.close()
    added = 0
    with zipfile.ZipFile(tmp.name, "w", zipfile.ZIP_DEFLATED) as z:
        for prod in prods:
            if added >= MAX_ZIP_FILES:
                break
            hit = _local_image(prod)
            if not hit:
                continue
            blob, ext = hit
            z.writestr(f"SP-{prod.id:06d}{ext}", blob)
            added += 1
    stamp = datetime.now().strftime("%Y%m%d")
    return FileResponse(
        tmp.name,
        media_type="application/zip",
        filename=f"shopee_images_{stamp}.zip",
        background=BackgroundTask(os.unlink, tmp.name),
    )
