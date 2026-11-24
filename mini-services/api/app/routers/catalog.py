"""Public storefront catalog API."""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import or_
from sqlalchemy.orm import Session

from .. import models
from ..database import get_db
from ..serializers import product_public

router = APIRouter(prefix="/api/catalog", tags=["catalog"])


def visible_query(db: Session):
    """Published products that belong to an ENABLED source (or to no source at all).
    Disabling a source in the admin panel instantly hides all of its content from
    the storefront; re-enabling brings it back. Data is never deleted."""
    return (
        db.query(models.Product)
        .outerjoin(models.Source, models.Product.source_id == models.Source.id)
        .filter(
            models.Product.status == "published",
            or_(
                models.Product.source_id.is_(None),
                models.Source.enabled == True,  # noqa: E712
            ),
        )
    )


@router.get("/theme")
def theme(db: Session = Depends(get_db)):
    """Public theme + typography configuration (applied by the storefront)."""
    rows = {r.key: r.value for r in db.query(models.Setting).filter(models.Setting.key.in_([
        "site_name", "theme_primary", "theme_accent", "theme_radius",
        "theme_dark_default", "fonts_family", "fonts_heading",
        "fonts_base_size", "fonts_heading_weight",
    ])).all()}
    return {
        "site_name": rows.get("site_name") or "Shopee",
        "theme": {
            "primary": rows.get("theme_primary") or "#EA580C",
            "accent": rows.get("theme_accent") or "#F59E0B",
            "radius": int(rows.get("theme_radius", 12) or 12),
            "dark_default": bool(rows.get("theme_dark_default", False)),
        },
        "fonts": {
            "family": rows.get("fonts_family") or "Inter",
            "heading": rows.get("fonts_heading") or "Inter",
            "base_size": int(rows.get("fonts_base_size", 16) or 16),
            "heading_weight": int(rows.get("fonts_heading_weight", 800) or 800),
        },
    }


@router.get("/categories")
def categories(db: Session = Depends(get_db)):
    cats = db.query(models.Category).order_by(models.Category.sort_order).all()
    out = []
    for c in cats:
        count = visible_query(db).filter(models.Product.category_id == c.id).count()
        out.append({"slug": c.slug, "name_en": c.name_en, "name_ko": c.name_ko, "product_count": count})
    return out


@router.get("/home")
def home(db: Session = Depends(get_db)):
    base = visible_query(db)
    featured = base.order_by(models.Product.reviews.desc()).limit(8).all()
    newest = base.order_by(models.Product.created_at.desc()).limit(8).all()
    cats = db.query(models.Category).order_by(models.Category.sort_order).all()
    settings_name = db.query(models.Setting).filter(models.Setting.key == "site_name").first()
    return {
        "site_name": settings_name.value if settings_name else "Shopee",
        "featured": [product_public(p) for p in featured],
        "newest": [product_public(p) for p in newest],
        "categories": [
            {"slug": c.slug, "name_en": c.name_en, "name_ko": c.name_ko} for c in cats
        ],
    }


@router.get("/products")
def products(
    q: str = "",
    category: str = "",
    sort: str = "newest",
    page: int = Query(1, ge=1),
    per_page: int = Query(24, ge=1, le=60),
    db: Session = Depends(get_db),
):
    query = visible_query(db)
    if category:
        cat = db.query(models.Category).filter(models.Category.slug == category).first()
        if cat:
            query = query.filter(models.Product.category_id == cat.id)
    if q:
        like = f"%{q}%"
        query = query.filter(or_(models.Product.title_en.ilike(like), models.Product.title_ko.ilike(like)))

    if sort == "price_asc":
        query = query.order_by(models.Product.price_sell.asc())
    elif sort == "price_desc":
        query = query.order_by(models.Product.price_sell.desc())
    elif sort == "popular":
        query = query.order_by(models.Product.reviews.desc())
    else:
        query = query.order_by(models.Product.created_at.desc())

    total = query.count()
    items = query.offset((page - 1) * per_page).limit(per_page).all()
    return {
        "items": [product_public(p) for p in items],
        "total": total,
        "page": page,
        "pages": max(1, (total + per_page - 1) // per_page),
    }


@router.get("/products/{slug}")
def product_detail(slug: str, db: Session = Depends(get_db)):
    p = (
        visible_query(db)
        .filter(models.Product.slug == slug)
        .first()
    )
    if not p:
        raise HTTPException(status_code=404, detail="Product not found")
    related = []
    if p.category_id:
        related = (
            visible_query(db)
            .filter(
                models.Product.category_id == p.category_id,
                models.Product.id != p.id,
            )
            .limit(4)
            .all()
        )
    d = product_public(p)
    d["related"] = [product_public(r) for r in related]
    return d
