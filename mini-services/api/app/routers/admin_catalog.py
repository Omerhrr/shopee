"""Admin: product & category management (CMS)."""
import hashlib

import httpx
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from pydantic import BaseModel
from sqlalchemy import or_
from sqlalchemy.orm import Session

from .. import models
from ..services import media_store
from ..database import get_db
from ..deps import get_current_admin
from ..serializers import product_admin
from ..services.markup import apply_pricing, reapply_all
from ..services.seed_service import _svg_placeholder
from ..services.translator import translate_product

router = APIRouter(prefix="/api/admin", tags=["admin-catalog"], dependencies=[Depends(get_current_admin)])

IMG_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0 Safari/537.36"
)


def _save_image_bytes(data: bytes, content_type: str) -> str:
    """Store image bytes under /media/uploads and return its public URL."""
    ext = "jpg"
    if "png" in content_type:
        ext = "png"
    elif "webp" in content_type:
        ext = "webp"
    elif "gif" in content_type:
        ext = "gif"
    elif "svg" in content_type:
        ext = "svg"
    name = hashlib.md5(data).hexdigest()[:16] + "." + ext
    return media_store.save(f"uploads/{name}", data, content_type.split(";")[0] or None)


@router.post("/upload-image")
async def upload_image(file: UploadFile = File(...)):
    """Upload an image file from the admin panel."""
    data = await file.read()
    content_type = (file.content_type or "").lower()
    if not content_type.startswith("image/"):
        raise HTTPException(400, "Only image files are allowed")
    if len(data) > 8 * 1024 * 1024:
        raise HTTPException(400, "File too large (max 8 MB)")
    if len(data) < 64:
        raise HTTPException(400, "File looks empty")
    return {"url": _save_image_bytes(data, content_type)}


class FetchImageIn(BaseModel):
    url: str


@router.post("/fetch-image")
def fetch_image(body: FetchImageIn):
    """Download a remote image into local storage so it always loads on the storefront
    (avoids hotlink blocks and dead source images)."""
    url = (body.url or "").strip()
    if not url.startswith(("http://", "https://")):
        raise HTTPException(400, "Enter a valid http(s) image URL")
    try:
        r = httpx.get(
            url,
            headers={"User-Agent": IMG_UA, "Referer": url, "Accept": "image/*,*/*"},
            timeout=20.0,
            follow_redirects=True,
        )
        ct = (r.headers.get("content-type") or "").lower()
        if r.status_code != 200 or not ct.startswith("image/") or len(r.content) < 512:
            raise HTTPException(400, f"Not a valid image response (status {r.status_code}, type {ct.split(';')[0] or 'unknown'})")
        return {"url": _save_image_bytes(r.content, ct)}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(400, f"Image download failed: {str(e)[:150]}")


class ProductIn(BaseModel):
    title_ko: str = ""
    title_en: str = ""
    desc_ko: str = ""
    desc_en: str = ""
    price_cost: int = 0
    markup_override: float | None = None
    images: list[str] = []
    status: str = "published"
    category_id: int | None = None
    stock_status: str = "in_stock"
    rating: float = 4.7
    reviews: int = 0


@router.get("/products")
def list_products(
    q: str = "",
    status: str = "",
    category_id: int | None = None,
    source_id: int | None = None,
    page: int = 1,
    per_page: int = 20,
    db: Session = Depends(get_db),
):
    page = max(1, page)
    per_page = max(1, min(per_page, 200))
    query = db.query(models.Product)
    if q:
        like = f"%{q}%"
        query = query.filter(or_(models.Product.title_ko.ilike(like), models.Product.title_en.ilike(like), models.Product.slug.ilike(like)))
    if status:
        query = query.filter(models.Product.status == status)
    if category_id:
        query = query.filter(models.Product.category_id == category_id)
    if source_id:
        query = query.filter(models.Product.source_id == source_id)
    total = query.count()
    items = (
        query.order_by(models.Product.created_at.desc())
        .offset((page - 1) * per_page)
        .limit(per_page)
        .all()
    )
    return {"items": [product_admin(p) for p in items], "total": total, "page": page,
            "pages": max(1, (total + per_page - 1) // per_page)}


@router.post("/products")
def create_product(body: ProductIn, db: Session = Depends(get_db)):
    if not body.title_ko and not body.title_en:
        raise HTTPException(400, "Title is required")
    body.title_ko, body.title_en = body.title_ko[:290], body.title_en[:290]
    seed = (body.title_en or body.title_ko)
    h = hashlib.md5((seed + str(body.price_cost)).encode()).hexdigest()[:6]
    slug = ("".join(ch for ch in seed.lower() if ch.isalnum() or ch in " -").strip().replace(" ", "-")[:80] or "item") + "-" + h
    i = 1
    base = slug
    while db.query(models.Product).filter(models.Product.slug == slug).first():
        i += 1
        slug = f"{base}-{i}"

    # Auto-generate a placeholder image if none provided
    images = [img for img in body.images if img]
    if not images:
        cat = db.query(models.Category).filter(models.Category.id == body.category_id).first()
        cat_slug = cat.slug if cat else "general"
        svg = _svg_placeholder(slug, body.title_ko or body.title_en, body.title_en or body.title_ko, "MANUAL", cat_slug)
        images = [media_store.save(f"seed/manual-{h}.svg", svg.encode("utf-8"), "image/svg+xml")]

    p = models.Product(
        slug=slug,
        title_ko=body.title_ko,
        title_en=body.title_en or None,
        desc_ko=body.desc_ko,
        desc_en=body.desc_en or None,
        price_cost=body.price_cost,
        markup_override=body.markup_override,
        images=images,
        status=body.status,
        category_id=body.category_id,
        stock_status=body.stock_status,
        rating=body.rating,
        reviews=body.reviews,
        is_manual=True,
        original_lang="ko" if body.title_ko and not body.title_en else "en",
        # one language missing -> translate the other side automatically
        translation_status="done" if (body.title_en and body.title_ko and
                                      (not (body.desc_ko or body.desc_en) or (body.desc_ko and body.desc_en))) else "pending",
    )
    apply_pricing(db, p)
    db.add(p)
    db.commit()
    return product_admin(p)


@router.get("/products/{pid}")
def get_product(pid: int, db: Session = Depends(get_db)):
    p = db.query(models.Product).filter(models.Product.id == pid).first()
    if not p:
        raise HTTPException(404, "Not found")
    return product_admin(p)


@router.put("/products/{pid}")
def update_product(pid: int, body: ProductIn, db: Session = Depends(get_db)):
    p = db.query(models.Product).filter(models.Product.id == pid).first()
    if not p:
        raise HTTPException(404, "Not found")
    p.title_ko = body.title_ko[:290]
    p.title_en = body.title_en[:290] or None
    p.desc_ko = body.desc_ko
    p.desc_en = body.desc_en or None
    p.price_cost = body.price_cost
    p.markup_override = body.markup_override
    if body.images:
        p.images = [img for img in body.images if img]
    p.status = body.status
    p.category_id = body.category_id
    p.stock_status = body.stock_status
    p.rating = body.rating
    p.reviews = body.reviews
    # a side left empty (or a description present in only one language) gets auto-translated
    both_titles = bool(body.title_en and body.title_ko)
    both_desc = (not (body.desc_ko or body.desc_en)) or bool(body.desc_ko and body.desc_en)
    p.translation_status = "done" if (both_titles and both_desc) else "pending"
    if not body.title_en and body.title_ko:
        p.original_lang = "ko"
    elif body.title_en and not body.title_ko:
        p.original_lang = "en"
    apply_pricing(db, p)
    db.commit()
    return product_admin(p)


@router.delete("/products/{pid}")
def delete_product(pid: int, db: Session = Depends(get_db)):
    p = db.query(models.Product).filter(models.Product.id == pid).first()
    if not p:
        raise HTTPException(404, "Not found")
    db.delete(p)
    db.commit()
    return {"ok": True}


@router.post("/products/{pid}/retranslate")
def retranslate(pid: int, db: Session = Depends(get_db)):
    p = db.query(models.Product).filter(models.Product.id == pid).first()
    if not p:
        raise HTTPException(404, "Not found")
    p.translation_status = "pending"
    # explicit retranslate: redo the machine-translated side
    if p.original_lang == "en":
        p.title_ko, p.desc_ko = "", ""
    else:
        p.title_en, p.desc_en = None, None
    db.commit()
    try:
        translate_product(db, p)
        db.commit()
        return {"ok": True, "title_en": p.title_en}
    except Exception as e:
        p.translation_status = "failed"
        db.commit()
        return {"ok": False, "error": str(e)[:300]}


class ReapplyIn(BaseModel):
    category_id: int | None = None


@router.post("/pricing/reapply")
def pricing_reapply(body: ReapplyIn, db: Session = Depends(get_db)):
    changed = reapply_all(db, body.category_id)
    return {"ok": True, "updated_products": changed}


# ---------- Categories ----------

class CategoryIn(BaseModel):
    slug: str
    name_en: str
    name_ko: str
    markup_percent: float | None = None
    sort_order: int = 0


@router.get("/categories")
def list_categories(db: Session = Depends(get_db)):
    cats = db.query(models.Category).order_by(models.Category.sort_order).all()
    out = []
    for c in cats:
        out.append({
            "id": c.id, "slug": c.slug, "name_en": c.name_en, "name_ko": c.name_ko,
            "markup_percent": c.markup_percent, "sort_order": c.sort_order,
            "product_count": db.query(models.Product).filter(models.Product.category_id == c.id).count(),
        })
    return out


@router.post("/categories")
def create_category(body: CategoryIn, db: Session = Depends(get_db)):
    if db.query(models.Category).filter(models.Category.slug == body.slug).first():
        raise HTTPException(400, "Slug already exists")
    c = models.Category(slug=body.slug, name_en=body.name_en, name_ko=body.name_ko,
                        markup_percent=body.markup_percent, sort_order=body.sort_order)
    db.add(c)
    db.commit()
    return {"id": c.id}


@router.put("/categories/{cid}")
def update_category(cid: int, body: CategoryIn, db: Session = Depends(get_db)):
    c = db.query(models.Category).filter(models.Category.id == cid).first()
    if not c:
        raise HTTPException(404, "Not found")
    if db.query(models.Category).filter(models.Category.slug == body.slug, models.Category.id != cid).first():
        raise HTTPException(400, "Slug already exists")
    c.slug = body.slug
    c.name_en = body.name_en
    c.name_ko = body.name_ko
    c.markup_percent = body.markup_percent
    c.sort_order = body.sort_order
    db.commit()
    return {"ok": True}


@router.delete("/categories/{cid}")
def delete_category(cid: int, db: Session = Depends(get_db)):
    c = db.query(models.Category).filter(models.Category.id == cid).first()
    if not c:
        raise HTTPException(404, "Not found")
    n = db.query(models.Product).filter(models.Product.category_id == cid).count()
    if n:
        raise HTTPException(400, f"Category has {n} products - move them first")
    db.delete(c)
    db.commit()
    return {"ok": True}
