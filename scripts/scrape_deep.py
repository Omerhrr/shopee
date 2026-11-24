"""Deeper scrape round for enabled working sources."""
import sys, time
sys.path.insert(0, "/home/z/my-project/mini-services/api")
from app.database import SessionLocal
from app import models
from app.services.scraper import scrape_source
from app.services.translator import run_pending_translations

db = SessionLocal()
try:
    rows = db.query(models.Source).filter(models.Source.enabled == True).all()  # noqa: E712
    print(f"{len(rows)} enabled sources")
    for s in rows:
        time.sleep(0.4)
        try:
            log = scrape_source(db, s, trigger="manual")
            has = db.query(models.Product).filter(models.Product.source_id == s.id).count()
            if log.status != "ok" or has == 0:
                s.enabled = False
                print(f"[{s.id}] {s.name}: FAIL -> disabled | {log.message[:80]}")
            else:
                print(f"[{s.id}] {s.name}: ok total={has} (+{log.new_products})")
        except Exception as e:
            s.enabled = False
            print(f"[{s.id}] {s.name}: EXC -> disabled")
        db.commit()
    total = db.query(models.Product).count()
    print(f"total products: {total}")
finally:
    db.close()

db = SessionLocal()
try:
    r = run_pending_translations(db, limit=80)
    print("translations:", r)
finally:
    db.close()
