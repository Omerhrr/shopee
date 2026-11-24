"""Admin: dashboard, finance summary, order management."""
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.orm import Session

from .. import models
from ..database import get_db
from ..deps import get_current_admin, get_setting
from ..serializers import order_admin
from ..services.translator import pending_count

router = APIRouter(prefix="/api/admin", tags=["admin-finance"], dependencies=[Depends(get_current_admin)])

VALID_STATUSES = ["pending", "paid", "packed", "shipped", "delivered", "cancelled"]


@router.get("/dashboard")
def dashboard(db: Session = Depends(get_db)):
    now = datetime.now(timezone.utc)
    day_ago = now - timedelta(days=1)
    orders = db.query(models.Order)
    orders_today = orders.filter(models.Order.created_at >= day_ago, models.Order.status != "cancelled")
    revenue_today = orders_today.with_entities(func.coalesce(func.sum(models.Order.total), 0)).scalar()
    profit_today = orders_today.with_entities(func.coalesce(func.sum(models.Order.profit), 0)).scalar()
    last_scrape = db.query(models.ScrapeLog).order_by(models.ScrapeLog.started_at.desc()).first()
    return {
        "products_total": db.query(models.Product).count(),
        "products_published": db.query(models.Product).filter(models.Product.status == "published").count(),
        "products_pending_translation": pending_count(db),
        "sources_total": db.query(models.Source).count(),
        "sources_enabled": db.query(models.Source).filter(models.Source.enabled == True).count(),  # noqa: E712
        "orders_today": orders_today.count(),
        "orders_total": orders.count(),
        "revenue_today": int(revenue_today or 0),
        "profit_today": int(profit_today or 0),
        "last_scrape": {
            "source": last_scrape.source_name if last_scrape else None,
            "status": last_scrape.status if last_scrape else None,
            "at": last_scrape.started_at.isoformat() if last_scrape and last_scrape.started_at else None,
            "message": last_scrape.message if last_scrape else None,
        },
    }


@router.get("/finance/summary")
def finance_summary(days: int = 30, db: Session = Depends(get_db)):
    since = datetime.now(timezone.utc) - timedelta(days=days)
    orders = (
        db.query(models.Order)
        .filter(models.Order.created_at >= since, models.Order.status != "cancelled")
        .all()
    )
    revenue = sum(o.total for o in orders)
    cost = sum(o.cost_total for o in orders)
    profit = sum(o.profit for o in orders)
    order_count = len(orders)

    daily = {}
    for o in orders:
        day = o.created_at.strftime("%m-%d") if o.created_at else "unknown"
        d = daily.setdefault(day, {"date": day, "revenue": 0, "profit": 0, "orders": 0})
        d["revenue"] += o.total
        d["profit"] += o.profit
        d["orders"] += 1
    series = [daily[k] for k in sorted(daily.keys())]

    top = (
        db.query(
            models.OrderItem.title_en,
            models.OrderItem.title_ko,
            func.sum(models.OrderItem.unit_sell * models.OrderItem.quantity).label("revenue"),
            func.sum(models.OrderItem.quantity).label("qty"),
        )
        .join(models.Order)
        .filter(models.Order.created_at >= since, models.Order.status != "cancelled")
        .group_by(models.OrderItem.title_en, models.OrderItem.title_ko)
        .order_by(func.sum(models.OrderItem.unit_sell * models.OrderItem.quantity).desc())
        .limit(8)
        .all()
    )
    status_counts = (
        db.query(models.Order.status, func.count(models.Order.id))
        .group_by(models.Order.status)
        .all()
    )
    return {
        "days": days,
        "revenue": revenue,
        "cost": cost,
        "profit": profit,
        "margin_pct": round(profit / revenue * 100, 1) if revenue else 0,
        "orders": order_count,
        "aov": round(revenue / order_count) if order_count else 0,
        "daily": series,
        "top_products": [
            {"title_en": t[0], "title_ko": t[1], "revenue": int(t[2]), "qty": int(t[3])} for t in top
        ],
        "status_counts": {s: c for s, c in status_counts},
    }


@router.get("/orders")
def list_orders(status: str = "", q: str = "", page: int = 1, per_page: int = 20, db: Session = Depends(get_db)):
    page = max(1, page)
    per_page = max(1, min(per_page, 200))
    query = db.query(models.Order)
    if status:
        query = query.filter(models.Order.status == status)
    if q:
        like = f"%{q}%"
        query = query.filter(
            (models.Order.order_number.ilike(like))
            | (models.Order.customer_name.ilike(like))
            | (models.Order.email.ilike(like))
        )
    total = query.count()
    items = query.order_by(models.Order.created_at.desc()).offset((page - 1) * per_page).limit(per_page).all()
    return {
        "items": [order_admin(o) for o in items],
        "total": total,
        "page": page,
        "pages": max(1, (total + per_page - 1) // per_page),
    }


@router.get("/orders/{oid}")
def get_order(oid: int, db: Session = Depends(get_db)):
    o = db.query(models.Order).filter(models.Order.id == oid).first()
    if not o:
        raise HTTPException(404, "Not found")
    return order_admin(o)


class StatusIn(BaseModel):
    status: str


@router.put("/orders/{oid}/status")
def update_status(oid: int, body: StatusIn, db: Session = Depends(get_db)):
    if body.status not in VALID_STATUSES:
        raise HTTPException(400, "Invalid status")
    o = db.query(models.Order).filter(models.Order.id == oid).first()
    if not o:
        raise HTTPException(404, "Not found")
    o.status = body.status
    db.commit()
    return order_admin(o)
