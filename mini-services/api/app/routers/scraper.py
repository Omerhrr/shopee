"""Scraper page backend: download the data OUR site already holds.

The site has already scraped Korean wholesale suppliers in bulk (admin
Sources panel). This router is the download side of that pipeline: browse or
search everything in the local catalog - published or not, from enabled or
deactivated sources - and pull any single listing as a Shopee-ready package
(1-row mass-upload CSV + Item-SKU-named images + plain-text info), ready to
post manually on shopee.kr until Open API access is approved.

No external requests are made here; every byte served comes from our own
database and media folder.
"""
import csv
import io
import os
import re
import tempfile
from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy import or_
from sqlalchemy.orm import Session, joinedload
from starlette.background import BackgroundTask

from .. import models
from ..services import media_store
from ..database import get_db
from ..deps import get_current_admin
from .admin_export import CSV_HEADERS

# Exposes wholesale cost + supplier URLs + unpublished items, so admin only.
router = APIRouter(prefix="/api/scraper", tags=["scraper-tool"], dependencies=[Depends(get_current_admin)])

ALLOWED_EXT = {".jpg", ".jpeg", ".png", ".webp"}


@router.get("/listings")
def listings(
    q: str = "",
    category: str = "",
    sort: str = "newest",
    page: int = 1,
    per_page: int = 24,
    db: Session = Depends(get_db),
):
    """Browse/search every product stored on this site (any status, any source).

    Unlike the storefront /catalog endpoint this is not filtered to
    status=published + enabled sources: the downloader should reach ALL the
    data the site holds, including listings from sources that were switched
    off in the admin panel. Filters and sort mirror the products page.
    """
    per_page = max(1, min(per_page, 60))
    page = max(1, page)
    query = db.query(models.Product).options(joinedload(models.Product.source))
    if category:
        cat = db.query(models.Category).filter(models.Category.slug == category).first()
        if cat:
            query = query.filter(models.Product.category_id == cat.id)
    term = (q or "").strip()
    if term:
        # Tokenized search (same rule as the storefront): every whitespace-
        # separated word must appear in the EN or KO title.
        for word in [w for w in re.split(r"\s+", term) if w]:
            like = f"%{word}%"
            query = query.filter(
                or_(
                    models.Product.title_en.ilike(like),
                    models.Product.title_ko.ilike(like),
                    models.Product.slug.ilike(like),
                )
            )

    if sort == "price_asc":
        query = query.order_by(models.Product.price_sell.asc())
    elif sort == "price_desc":
        query = query.order_by(models.Product.price_sell.desc())
    elif sort == "popular":
        query = query.order_by(models.Product.reviews.desc())
    else:
        query = query.order_by(models.Product.created_at.desc())

    total = query.count()
    rows = query.offset((page - 1) * per_page).limit(per_page).all()
    items = []
    for p in rows:
        imgs = [i for i in (p.images or []) if isinstance(i, str) and i.strip()]
        items.append(
            {
                "id": p.id,
                "sku": f"SP-{p.id:06d}",
                "title_ko": p.title_ko or "",
                "title_en": (p.title_en or "").strip(),
                "price_cost": p.price_cost,
                "price_sell": p.price_sell,
                "thumb": imgs[0] if imgs else "",
                "image_count": len(imgs),
                "images": imgs,
                "desc_ko": p.desc_ko or "",
                "desc_en": (p.desc_en or "").strip(),
                "status": p.status,
                "translation_status": p.translation_status,
                "source_name": p.source.name if p.source else "",
                "source_enabled": bool(p.source.enabled) if p.source else False,
                "source_url": p.source_url or "",
            }
        )
    return {
        "items": items,
        "total": total,
        "page": page,
        "pages": max(1, (total + per_page - 1) // per_page),
    }


@router.get("/categories")
def categories(db: Session = Depends(get_db)):
    """Category list with counts over ALL stored products (no visibility
    filter) so the downloader sidebar reflects the real data held on site."""
    cats = db.query(models.Category).order_by(models.Category.sort_order).all()
    out = []
    for c in cats:
        count = db.query(models.Product).filter(models.Product.category_id == c.id).count()
        out.append(
            {
                "slug": c.slug,
                "name_en": c.name_en,
                "name_ko": c.name_ko,
                "product_count": count,
            }
        )
    return out


def _local_files(images: list) -> list[tuple[bytes, str]]:
    """Stored images -> [(bytes, ext)], de-duplicated, only Shopee-friendly formats."""
    out: list[tuple[bytes, str]] = []
    seen: set[str] = set()
    for e in images or []:
        if not isinstance(e, str) or not e.strip() or e.startswith(("http://", "https://")):
            continue
        rel = media_store.clean_rel(e)
        if rel in seen:
            continue
        seen.add(rel)
        ext = os.path.splitext(rel)[1].lower()
        if ext not in ALLOWED_EXT:
            continue
        hit = media_store.load(rel)
        if hit and len(hit[0]) > 512:
            out.append((hit[0], ".jpg" if ext == ".jpeg" else ext))
    return out


class PackageIn(BaseModel):
    product_id: int
    price_mode: str = "sell"          # sell (retail incl. markup) | cost (wholesale)
    currency: str = "KRW"             # KRW | USD
    usd_rate: float = 1350.0
    stock: int = 10
    weight_g: int = 500
    length_cm: float = 25
    width_cm: float = 20
    height_cm: float = 10
    public_base: str = "http://localhost:3000"


@router.post("/package")
def package(body: PackageIn, db: Session = Depends(get_db)):
    """Download one listing from our catalog as a Shopee-ready ZIP
    (CSV row + SKU-named images + plain-text listing info)."""
    p = db.query(models.Product).filter(models.Product.id == body.product_id).first()
    if not p:
        raise HTTPException(404, "Product not found")

    sku = f"SP-{p.id:06d}"
    title = (p.title_en or "").strip() or (p.title_ko or "").strip()
    desc = (p.desc_en or "").strip() or (p.desc_ko or "").strip()
    files = _local_files(p.images or [])
    if not files:
        raise HTTPException(422, "No local images available for this listing")

    data = {
        "sku": sku,
        "title_ko": (p.title_ko or "")[:290],
        "title_en": (p.title_en or "").strip(),
        "desc_ko": p.desc_ko or "",
        "desc_en": (p.desc_en or "").strip(),
        "title": title[:255],
        "desc": " ".join(desc.split())[:3000],
        "price_cost": p.price_cost,
        "price_sell": p.price_sell,
        "images": p.images or [],
        "files": files,
        "source_url": p.source_url or "",
    }

    base = data["price_sell"] if body.price_mode == "sell" else data["price_cost"]
    cur = body.currency.upper()
    price = round(base / body.usd_rate, 2) if (cur == "USD" and body.usd_rate > 0) else base

    urls = []
    for img in data["images"]:
        if isinstance(img, str) and img.strip():
            u = img.strip()
            urls.append(u if u.startswith(("http://", "https://")) else body.public_base.rstrip("/") + "/" + u.lstrip("/"))
        if len(urls) >= 5:
            break
    imgs = list(urls) + [""] * (5 - len(urls))

    csv_buf = io.StringIO()
    w = csv.writer(csv_buf)
    w.writerow(CSV_HEADERS)
    w.writerow([
        "", data["title"], data["desc"], price, max(1, int(body.stock)), data["sku"], "",
        *imgs, body.weight_g, body.length_cm, body.width_cm, body.height_cm,
    ])
    csv_bytes = b"\xef\xbb\xbf" + csv_buf.getvalue().encode("utf-8")

    price_lines = f"Retail price: {price} {cur}"
    if cur == "USD":
        price_lines += f"  (KRW {data['price_sell']:,})"
    price_lines += f"\nWholesale cost: KRW {data['price_cost']:,}"

    listing_txt = (
        "SHOPEE LISTING - ready to post\n"
        "==============================\n"
        f"Generated: {date.today().isoformat()}\n"
        f"Item SKU: {data['sku']}\n"
        f"Product name: {data['title']}\n"
        f"{price_lines}\n"
        f"\nDescription:\n{data['desc'] or '(none)'}\n"
        f"\nSource page: {data['source_url'] or '(catalog item)'}\n"
        "\nHOW TO USE\n"
        "- images/ holds the photos; the _1 file is the MAIN image.\n"
        "- shopee_listing.csv uses the Shopee mass-upload columns: paste the row into the\n"
        "  official template (fill Category ID) or copy the fields into Seller Center.\n"
        "- Keep the Item SKU unchanged.\n"
    )

    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".zip")
    tmp.close()
    from zipfile import ZIP_DEFLATED, ZIP_STORED, ZipFile

    with ZipFile(tmp.name, "w") as z:
        z.writestr("listing.txt", listing_txt, compress_type=ZIP_DEFLATED)
        z.writestr("shopee_listing.csv", csv_bytes, compress_type=ZIP_DEFLATED)
        for i, (blob, ext) in enumerate(data["files"], start=1):
            z.writestr(f"images/{data['sku']}_{i}{ext}", blob, compress_type=ZIP_STORED)

    return FileResponse(
        tmp.name,
        media_type="application/zip",
        filename=f"shopee_listing_{data['sku']}.zip",
        background=BackgroundTask(os.unlink, tmp.name),
    )
