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
from ..services.images import fetch_download_images, fetch_download_images_many, proxy_path, proxy_url, unproxy
from ..services.translator import ensure_translated
from ..database import get_db
from ..deps import get_current_admin, get_setting
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
    lang: str = "",
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
    if lang in ("en", "ko"):
        try:  # translate what is missing on THIS page so names always show in the chosen language
            ensure_translated(db, rows, lang, budget_s=20)
        except Exception:
            db.rollback()
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
                "thumb": proxy_url(imgs[0]) if imgs else "",
                "image_count": len(imgs),
                "images": [proxy_url(i) for i in imgs],
                "desc_ko": p.desc_ko or "",
                "desc_en": (p.desc_en or "").strip(),
                "status": p.status,
                "translation_status": p.translation_status,
                "source_name": p.source.name if p.source else "",
                "source_name_en": ((p.source.config or {}).get("name_en") or p.source.name) if p.source else "",
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
    """Product images as [(bytes, ext)]: fetched from the supplier at download time (we store only the URL);
    older products that still have a stored copy are read from storage."""
    return fetch_download_images(images, limit=5)


def _zip_enabled(db: Session) -> bool:
    v = get_setting(db, "download_zip_enabled", True)
    return v if isinstance(v, bool) else str(v).lower() in ("1", "true", "yes", "on")


def _require_zip(db: Session) -> None:
    if not _zip_enabled(db):
        raise HTTPException(403, "ZIP downloads are turned off (Admin > Settings > Downloads). Use the Excel download.")


@router.get("/options")
def options(db: Session = Depends(get_db)):
    """What the downloader page may offer (set in Admin > Settings > Downloads)."""
    return {"zip_enabled": _zip_enabled(db)}


class PackageIn(BaseModel):
    product_id: int
    lang: str = "en"                  # en | ko
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
    _require_zip(db)
    p = db.query(models.Product).filter(models.Product.id == body.product_id).first()
    if not p:
        raise HTTPException(404, "Product not found")

    sku = f"SP-{p.id:06d}"
    try:
        ensure_translated(db, [p], body.lang, budget_s=20)
    except Exception:
        db.rollback()
    if body.lang == "ko":
        title = (p.title_ko or "").strip() or (p.title_en or "").strip()
        desc = (p.desc_ko or "").strip() or (p.desc_en or "").strip()
    else:
        title = (p.title_en or "").strip() or (p.title_ko or "").strip()
        desc = (p.desc_en or "").strip() or (p.desc_ko or "").strip()
    files = _local_files(p.images or [])
    if not files:
        raise HTTPException(422, "The supplier image could not be downloaded right now. Try again in a moment.")

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
            u = unproxy(img.strip())
            urls.append(body.public_base.rstrip("/") + proxy_path(u) if u.startswith(("http://", "https://")) else body.public_base.rstrip("/") + "/" + u.lstrip("/"))
        if len(urls) >= 5:
            break
    imgs = list(urls) + [""] * (5 - len(urls))

    csv_buf = io.StringIO()
    w = csv.writer(csv_buf)
    w.writerow(CSV_HEADERS)
    w.writerow([
        "", data["title"], data["desc"], price, max(1, int(body.stock)), data["sku"], "",
        *imgs, body.weight_g, body.length_cm, body.width_cm, body.height_cm, data["source_url"],
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


# ---------------------------------------------------------------- bulk selection
MAX_IDS = 5000          # "select all results" cap
MAX_PACKAGE_ITEMS = 100  # products per ZIP: images are fetched live from the suppliers (time limit on serverless hosts)


def _filtered_query(db: Session, q: str, category: str):
    query = db.query(models.Product)
    if category:
        cat = db.query(models.Category).filter(models.Category.slug == category).first()
        if cat:
            query = query.filter(models.Product.category_id == cat.id)
    for word in [w for w in re.split(r"\s+", (q or "").strip()) if w]:
        like = f"%{word}%"
        query = query.filter(
            or_(models.Product.title_en.ilike(like), models.Product.title_ko.ilike(like), models.Product.slug.ilike(like))
        )
    return query


@router.get("/ids")
def listing_ids(q: str = "", category: str = "", db: Session = Depends(get_db)):
    """Ids of EVERY listing matching the current search/category (for 'select all results')."""
    rows = _filtered_query(db, q, category).order_by(models.Product.created_at.desc()).limit(MAX_IDS + 1).all()
    ids = [p.id for p in rows[:MAX_IDS]]
    return {"ids": ids, "total": len(ids), "capped": len(rows) > MAX_IDS}


class MultiPackageIn(BaseModel):
    product_ids: list[int]
    lang: str = "en"                  # en | ko : which title/description goes in the CSV
    price_mode: str = "sell"
    currency: str = "KRW"
    usd_rate: float = 1350.0
    stock: int = 10
    weight_g: int = 500
    length_cm: float = 25
    width_cm: float = 20
    height_cm: float = 10
    public_base: str = "http://localhost:3000"


@router.post("/package-multi")
def package_multi(body: MultiPackageIn, db: Session = Depends(get_db)):
    """Several listings in ONE ZIP: combined shopee CSV (one row each), listings.txt,
    images/<SKU>_<n>.ext. Items without a usable stored image are listed in skipped.txt."""
    _require_zip(db)
    ids = list(dict.fromkeys(body.product_ids))
    if not ids:
        raise HTTPException(400, "Nothing selected")
    if len(ids) > MAX_PACKAGE_ITEMS:
        raise HTTPException(400, f"Max {MAX_PACKAGE_ITEMS} listings per download")
    prods = {p.id: p for p in db.query(models.Product).filter(models.Product.id.in_(ids)).all()}
    try:  # fill the missing language side for the whole batch first (parallel, time boxed)
        ensure_translated(db, list(prods.values()), body.lang, budget_s=45, max_items=MAX_PACKAGE_ITEMS)
    except Exception:
        db.rollback()

    cur = body.currency.upper()
    csv_buf = io.StringIO()
    w = csv.writer(csv_buf)
    w.writerow(CSV_HEADERS)
    txt, skipped, files = [], [], []
    order_ids = [pid for pid in ids if pid in prods]
    got_all = dict(zip(order_ids, fetch_download_images_many([prods[pid].images or [] for pid in order_ids], limit=5)))
    for pid in ids:
        p = prods.get(pid)
        if not p:
            skipped.append(f"id {pid}: not found")
            continue
        sku = f"SP-{p.id:06d}"
        imgs_local = got_all.get(pid) or []
        if not imgs_local:
            skipped.append(f"{sku}: image could not be downloaded from the supplier")
            continue
        if body.lang == "ko":
            title = (p.title_ko or "").strip() or (p.title_en or "").strip()
            desc = (p.desc_ko or "").strip() or (p.desc_en or "").strip()
        else:
            title = (p.title_en or "").strip() or (p.title_ko or "").strip()
            desc = (p.desc_en or "").strip() or (p.desc_ko or "").strip()
        title, desc = title[:255], " ".join(desc.split())[:3000]
        base = p.price_sell if body.price_mode == "sell" else p.price_cost
        price = round(base / body.usd_rate, 2) if (cur == "USD" and body.usd_rate > 0) else base
        urls = []
        for img in p.images or []:
            if isinstance(img, str) and img.strip():
                u = unproxy(img.strip())
                urls.append(body.public_base.rstrip("/") + proxy_path(u) if u.startswith(("http://", "https://")) else body.public_base.rstrip("/") + "/" + u.lstrip("/"))
            if len(urls) >= 5:
                break
        urls += [""] * (5 - len(urls))
        w.writerow(["", title, desc, price, max(1, int(body.stock)), sku, "", *urls,
                    body.weight_g, body.length_cm, body.width_cm, body.height_cm, p.source_url or ""])
        txt.append(f"{sku} | {title}\n  price {price} {cur} | cost KRW {p.price_cost:,} | {p.source_url or '(catalog item)'}\n")
        for i, (blob, ext) in enumerate(imgs_local, start=1):
            files.append((f"images/{sku}_{i}{ext}", blob))

    if not files:
        raise HTTPException(422, "The supplier images could not be downloaded right now. Try again in a moment.")

    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".zip")
    tmp.close()
    from zipfile import ZIP_DEFLATED, ZIP_STORED, ZipFile

    with ZipFile(tmp.name, "w") as z:
        z.writestr("shopee_listings.csv", b"\xef\xbb\xbf" + csv_buf.getvalue().encode("utf-8"), compress_type=ZIP_DEFLATED)
        z.writestr("listings.txt", f"SHOPEE LISTINGS ({len(txt)})  generated {date.today().isoformat()}\n\n" + "\n".join(txt), compress_type=ZIP_DEFLATED)
        if skipped:
            z.writestr("skipped.txt", "\n".join(skipped), compress_type=ZIP_DEFLATED)
        for name, blob in files:
            z.writestr(name, blob, compress_type=ZIP_STORED)

    return FileResponse(
        tmp.name,
        media_type="application/zip",
        filename=f"shopee_listings_{len(txt)}_items.zip",
        background=BackgroundTask(os.unlink, tmp.name),
        headers={"X-Skipped": str(len(skipped)), "Access-Control-Expose-Headers": "X-Skipped"},
    )


# ---------------------------------------------------------------- Excel (.xlsx) only
MAX_EXCEL_ITEMS = 500  # per file (thumbnails + on-demand translation time)


class ExcelIn(BaseModel):
    product_ids: list[int]
    lang: str = "en"
    price_mode: str = "sell"
    currency: str = "KRW"
    usd_rate: float = 1350.0
    stock: int = 10
    weight_g: int = 500
    length_cm: float = 25
    width_cm: float = 20
    height_cm: float = 10
    public_base: str = "http://localhost:3000"


@router.post("/excel")
def excel(body: ExcelIn, db: Session = Depends(get_db)):
    """Selected listings as ONE formatted Excel file (no images inside the download, only links)."""
    from fastapi.responses import Response

    from ..services.xlsx_export import build_workbook

    ids = list(dict.fromkeys(body.product_ids))
    if not ids:
        raise HTTPException(400, "Nothing selected")
    if len(ids) > MAX_EXCEL_ITEMS:
        raise HTTPException(400, f"Max {MAX_EXCEL_ITEMS} listings per Excel file")
    prods = {p.id: p for p in db.query(models.Product).filter(models.Product.id.in_(ids)).all()}
    try:
        ensure_translated(db, list(prods.values()), body.lang, budget_s=45, max_items=MAX_EXCEL_ITEMS)
    except Exception:
        db.rollback()

    cur = body.currency.upper()
    rows = []
    order_ids = [pid for pid in ids if pid in prods]
    thumbs = dict(zip(order_ids, fetch_download_images_many([(prods[pid].images or [])[:1] for pid in order_ids], limit=1, workers=10)))
    for pid in ids:
        p = prods.get(pid)
        if not p:
            continue
        sku = f"SP-{p.id:06d}"
        if body.lang == "ko":
            title = (p.title_ko or "").strip() or (p.title_en or "").strip()
            desc = (p.desc_ko or "").strip() or (p.desc_en or "").strip()
        else:
            title = (p.title_en or "").strip() or (p.title_ko or "").strip()
            desc = (p.desc_en or "").strip() or (p.desc_ko or "").strip()
        title, desc = title[:255], " ".join(desc.split())[:3000]
        base = p.price_sell if body.price_mode == "sell" else p.price_cost
        price = round(base / body.usd_rate, 2) if (cur == "USD" and body.usd_rate > 0) else base
        urls = []
        for img in p.images or []:
            if isinstance(img, str) and img.strip():
                u = unproxy(img.strip())
                urls.append(body.public_base.rstrip("/") + proxy_path(u) if u.startswith(("http://", "https://")) else body.public_base.rstrip("/") + "/" + u.lstrip("/"))
            if len(urls) >= 5:
                break
        urls += [""] * (5 - len(urls))
        got = thumbs.get(pid) or []
        thumb = got[0][0] if got else None
        rows.append({
            "cells": ["", title, desc, price, max(1, int(body.stock)), sku, "", *urls,
                      body.weight_g, body.length_cm, body.width_cm, body.height_cm, p.source_url or ""],
            "sku": sku, "title": title, "price": price, "cost": p.price_cost or 0,
            "source_url": p.source_url or "", "thumb": thumb,
        })
    if not rows:
        raise HTTPException(404, "Nothing found")

    meta = {
        "price_fmt": "#,##0.00" if cur == "USD" else "#,##0",
        "price_label": f"Price ({cur})",
        "lang_label": "Korean" if body.lang == "ko" else "English",
        "price_note": f"{'Retail (incl. markup)' if body.price_mode == 'sell' else 'Wholesale cost'} in {cur}",
    }
    data = build_workbook(CSV_HEADERS, rows, meta)
    return Response(
        content=data,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="shopee_listings_{len(rows)}_items.xlsx"'},
    )
