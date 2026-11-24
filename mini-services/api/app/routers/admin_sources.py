"""Admin: supplier sources + scraping control (sources seeded from the uploaded Excel list)."""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from .. import models
from ..database import get_db
import time

from ..config import IS_VERCEL
from ..deps import get_current_admin, get_setting, set_setting
from ..serializers import source_admin
from ..services.scraper import collect_product_urls, extract_product, fetch_html, scrape_all_enabled, scrape_source, make_client
from ..services.scheduler import next_run_times, reschedule_scrape

router = APIRouter(prefix="/api/admin", tags=["admin-sources"], dependencies=[Depends(get_current_admin)])


@router.get("/sources")
def list_sources(q: str = "", enabled: str = "", db: Session = Depends(get_db)):
    query = db.query(models.Source)
    if q:
        like = f"%{q}%"
        query = query.filter(
            (models.Source.name.ilike(like))
            | (models.Source.category_hint.ilike(like))
            | (models.Source.url.ilike(like))
        )
    if enabled == "true":
        query = query.filter(models.Source.enabled == True)  # noqa: E712
    elif enabled == "false":
        query = query.filter(models.Source.enabled == False)  # noqa: E712
    sources = query.order_by(models.Source.name).all()
    return [source_admin(s) for s in sources]


class SourceIn(BaseModel):
    name: str
    url: str = ""
    adapter: str = "generic"
    config: dict = {}
    enabled: bool = False
    notes: str = ""
    contact: str = ""


@router.post("/sources")
def create_source(body: SourceIn, db: Session = Depends(get_db)):
    s = models.Source(
        name=body.name, url=body.url, adapter=body.adapter, config=body.config,
        enabled=body.enabled, notes=body.notes, contact=body.contact, status="new",
    )
    db.add(s)
    db.commit()
    return source_admin(s)


@router.put("/sources/{sid}")
def update_source(sid: int, body: SourceIn, db: Session = Depends(get_db)):
    s = db.query(models.Source).filter(models.Source.id == sid).first()
    if not s:
        raise HTTPException(404, "Not found")
    was_enabled = s.enabled
    s.name = body.name
    s.url = body.url
    s.adapter = body.adapter
    s.config = body.config
    s.enabled = body.enabled
    s.notes = body.notes
    s.contact = body.contact
    # Deactivating a source hides ALL of its products from the storefront,
    # re-activating it brings them back. Products are kept in the database.
    if was_enabled and not body.enabled:
        db.query(models.Product).filter(models.Product.source_id == sid).update(
            {models.Product.status: "archived"}, synchronize_session=False
        )
    elif not was_enabled and body.enabled:
        db.query(models.Product).filter(
            models.Product.source_id == sid, models.Product.status == "archived"
        ).update({models.Product.status: "published"}, synchronize_session=False)
    db.commit()
    return source_admin(s)


@router.delete("/sources/{sid}")
def delete_source(sid: int, db: Session = Depends(get_db)):
    s = db.query(models.Source).filter(models.Source.id == sid).first()
    if not s:
        raise HTTPException(404, "Not found")
    # Real-data policy: deleting a source removes its products. Products that are
    # referenced by order items are kept (order history integrity) but archived.
    pids = [pid for (pid,) in db.query(models.Product.id).filter(models.Product.source_id == sid).all()]
    if pids:
        ordered = {
            row[0]
            for row in db.query(models.OrderItem.product_id)
            .filter(models.OrderItem.product_id.in_(pids))
            .all()
            if row[0] is not None
        }
        deletable = [pid for pid in pids if pid not in ordered]
        if deletable:
            db.query(models.Product).filter(models.Product.id.in_(deletable)).delete(synchronize_session=False)
        if ordered:
            db.query(models.Product).filter(models.Product.id.in_(list(ordered))).update(
                {models.Product.source_id: None, models.Product.status: "archived"}, synchronize_session=False
            )
    db.delete(s)
    db.commit()
    return {"ok": True}


@router.post("/sources/{sid}/scrape")
def scrape_now(sid: int, db: Session = Depends(get_db)):
    s = db.query(models.Source).filter(models.Source.id == sid).first()
    if not s:
        raise HTTPException(404, "Not found")
    log = scrape_source(db, s, trigger="manual", deadline=(time.time() + 240) if IS_VERCEL else None)
    return {"ok": log.status == "ok", "status": log.status, "new": log.new_products,
            "updated": log.updated_products, "message": log.message}


@router.post("/scrape/run-all")
def scrape_run_all(db: Session = Depends(get_db)):
    results = scrape_all_enabled(db, trigger="manual", deadline=(time.time() + 240) if IS_VERCEL else None)
    return {"ok": True, "results": results}


@router.post("/sources/{sid}/test")
def test_source(sid: int, db: Session = Depends(get_db)):
    """Dry-run: fetch the listing page and show what WOULD be parsed (nothing saved)."""
    s = db.query(models.Source).filter(models.Source.id == sid).first()
    if not s:
        raise HTTPException(404, "Not found")
    listing = (s.config or {}).get("listing_url") or s.url
    if not listing:
        return {"ok": False, "error": "No URL configured"}
    try:
        client = make_client()
        urls, drilled = collect_product_urls(client, listing, 6)
        sample = []
        for u in urls[:3]:
            try:
                item = extract_product(fetch_html(client, u), u)
                if item:
                    sample.append({"url": u, "title": item.get("title"), "price": item.get("price")})
            except Exception:
                pass
        client.close()
        return {"ok": True, "found_links": len(urls), "drilled": drilled, "samples": sample}
    except Exception as e:
        return {"ok": False, "error": str(e)[:300]}


@router.get("/scrape/logs")
def scrape_logs(limit: int = 50, db: Session = Depends(get_db)):
    logs = (
        db.query(models.ScrapeLog)
        .order_by(models.ScrapeLog.started_at.desc())
        .limit(limit)
        .all()
    )
    return [
        {
            "id": l.id, "source_name": l.source_name, "trigger": l.trigger, "status": l.status,
            "new_products": l.new_products, "updated_products": l.updated_products,
            "message": l.message, "started_at": l.started_at.isoformat() if l.started_at else None,
        }
        for l in logs
    ]


@router.get("/scrape/schedule")
def scrape_schedule(db: Session = Depends(get_db)):
    return {
        "interval_minutes": int(get_setting(db, "scrape_interval_minutes", 360)),
        "enabled": bool(get_setting(db, "scrape_enabled", True)),
        "max_products_per_run": int(get_setting(db, "scrape_max_products_per_run", 10)),
        "next_runs": next_run_times(),
    }


class ScheduleIn(BaseModel):
    interval_minutes: int
    enabled: bool
    max_products_per_run: int = 10


@router.put("/scrape/schedule")
def update_schedule(body: ScheduleIn, db: Session = Depends(get_db)):
    interval = max(5, int(body.interval_minutes))
    set_setting(db, "scrape_interval_minutes", interval)
    set_setting(db, "scrape_enabled", body.enabled)
    set_setting(db, "scrape_max_products_per_run", max(1, min(body.max_products_per_run, 50)))
    db.commit()
    reschedule_scrape()
    return scrape_schedule(db)
