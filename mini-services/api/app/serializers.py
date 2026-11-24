"""Serialization helpers: public (customer) vs admin (full) product views."""
from . import models


def product_public(p: models.Product, lang_hint: str = "en") -> dict:
    cat = p.category
    return {
        "id": p.id,
        "slug": p.slug,
        "title_ko": p.title_ko,
        "title_en": p.title_en,
        "desc_ko": p.desc_ko,
        "desc_en": p.desc_en,
        "price_sell": p.price_sell,
        "images": p.images or [],
        "rating": p.rating,
        "reviews": p.reviews,
        "stock_status": p.stock_status,
        "translation_status": p.translation_status,
        "original_lang": p.original_lang,
        "category": {"slug": cat.slug, "name_en": cat.name_en, "name_ko": cat.name_ko} if cat else None,
        "created_at": p.created_at.isoformat() if p.created_at else None,
    }


def product_admin(p: models.Product) -> dict:
    d = product_public(p)
    src = p.source
    d.update(
        {
            "price_cost": p.price_cost,
            "markup_override": p.markup_override,
            "effective_margin_pct": round(
                (p.price_sell - p.price_cost) / p.price_cost * 100.0, 1
            )
            if p.price_cost
            else 0,
            "status": p.status,
            "is_manual": p.is_manual,
            "source_id": p.source_id,
            "source_name": src.name if src else None,
            "source_name_en": ((src.config or {}).get("name_en") or src.name) if src else None,
            "source_url": p.source_url,
            "category_id": p.category_id,
            "updated_at": p.updated_at.isoformat() if p.updated_at else None,
        }
    )
    return d


def order_admin(o: models.Order) -> dict:
    return {
        "id": o.id,
        "order_number": o.order_number,
        "customer_name": o.customer_name,
        "email": o.email,
        "phone": o.phone,
        "address1": o.address1,
        "address2": o.address2,
        "city": o.city,
        "postal_code": o.postal_code,
        "memo": o.memo,
        "status": o.status,
        "payment_method": o.payment_method,
        "locale": o.locale,
        "subtotal": o.subtotal,
        "shipping": o.shipping,
        "total": o.total,
        "cost_total": o.cost_total,
        "profit": o.profit,
        "created_at": o.created_at.isoformat() if o.created_at else None,
        "items": [
            {
                "id": i.id,
                "product_id": i.product_id,
                "title_ko": i.title_ko,
                "title_en": i.title_en,
                "image": i.image,
                "unit_sell": i.unit_sell,
                "unit_cost": i.unit_cost,
                "quantity": i.quantity,
            }
            for i in o.items
        ],
    }


def order_public(o: models.Order) -> dict:
    """Customer-facing order view: no wholesale cost, no profit."""
    return {
        "order_number": o.order_number,
        "customer_name": o.customer_name,
        "address1": o.address1,
        "address2": o.address2,
        "status": o.status,
        "payment_method": o.payment_method,
        "subtotal": o.subtotal,
        "shipping": o.shipping,
        "total": o.total,
        "created_at": o.created_at.isoformat() if o.created_at else None,
        "items": [
            {"id": i.id, "title_ko": i.title_ko, "title_en": i.title_en, "image": i.image,
             "unit_sell": i.unit_sell, "quantity": i.quantity}
            for i in o.items
        ],
    }


def source_admin(s: models.Source) -> dict:
    return {
        "id": s.id,
        "name": s.name,
        "url": s.url,
        "name_en": (s.config or {}).get("name_en") or s.name,
        "category_hint": s.category_hint,
        "category_hint_en": (s.config or {}).get("category_hint_en") or s.category_hint,
        "products_hint": s.products_hint,
        "contact": s.contact,
        "notes": s.notes,
        "image_provided": s.image_provided,
        "dropship_possible": s.dropship_possible,
        "paid_membership": s.paid_membership,
        "requires_cafe": s.requires_cafe,
        "adapter": s.adapter,
        "config": s.config or {},
        "enabled": s.enabled,
        "status": s.status,
        "last_scraped_at": s.last_scraped_at.isoformat() if s.last_scraped_at else None,
        "last_error": s.last_error,
        "product_count": len(s.products) if s.products else 0,
        "category_id": (s.config or {}).get("category_id"),
    }
