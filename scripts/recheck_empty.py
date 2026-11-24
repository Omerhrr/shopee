"""Scrape enabled sources that still have zero products; disable the ones that fail (new logic marks errors properly)."""
import sys, time
sys.path.insert(0, "/home/z/my-project/mini-services/api")
from app.database import SessionLocal
from app import models
from app.services.scraper import scrape_source

db = SessionLocal()
try:
    rows = db.query(models.Source).filter(models.Source.enabled == True).all()  # noqa: E712
    todo = [s for s in rows if db.query(models.Product).filter(models.Product.source_id == s.id).count() == 0]
    print(f"{len(todo)} empty enabled sources to re-check")
    for s in todo:
        time.sleep(0.4)
        try:
            log = scrape_source(db, s, trigger="manual")
            has = db.query(models.Product).filter(models.Product.source_id == s.id).count()
            if log.status != "ok" or has == 0:
                s.enabled = False
                print(f"[{s.id}] {s.name}: FAIL -> disabled | {log.message[:110]}")
            else:
                print(f"[{s.id}] {s.name}: OK +{log.new_products}")
        except Exception as e:
            s.enabled = False
            print(f"[{s.id}] {s.name}: EXC {type(e).__name__} -> disabled")
        db.commit()
    enabled = db.query(models.Source).filter(models.Source.enabled == True).count()  # noqa: E712
    total = db.query(models.Product).count()
    real = db.query(models.Product).filter(models.Product.is_manual == False).count()  # noqa: E712
    print(f"enabled: {enabled} | products: {total} (scraped: {real})")
finally:
    db.close()
