"""Run initial scrapes for enabled sources with no products yet + translations after.
Run with the backend venv python. Safe to re-run (upserts skip existing products)."""
import sys
import time

sys.path.insert(0, "/home/z/my-project/mini-services/api")

from app.database import SessionLocal
from app import models
from app.services.scraper import scrape_source
from app.services.translator import run_pending_translations

MAX_SECONDS = float(sys.argv[1]) if len(sys.argv) > 1 else 480.0

def main():
    start = time.time()
    db = SessionLocal()
    try:
        rows = (
            db.query(models.Source)
            .filter(models.Source.enabled == True)  # noqa: E712
            .all()
        )
        todo = [s for s in rows if db.query(models.Product).filter(models.Product.source_id == s.id).count() == 0]
        print(f"{len(todo)} sources to scrape (of {len(rows)} enabled)")
        for s in todo:
            if time.time() - start > MAX_SECONDS:
                print(f"time budget reached, stopping (remaining {len(todo) - todo.index(s)})")
                break
            t0 = time.time()
            try:
                log = scrape_source(db, s, trigger="manual")
                print(f"[{s.id}] {s.name}: {log.status} +{log.new_products}/~{log.updated_products} "
                      f"({time.time() - t0:.1f}s) {log.message[:100]}")
            except Exception as e:
                print(f"[{s.id}] {s.name}: EXC {type(e).__name__} {str(e)[:100]}")
        total = db.query(models.Product).count()
        print(f"total products now: {total}")
    finally:
        db.close()

    # translations for pending items (google_free)
    db = SessionLocal()
    try:
        r = run_pending_translations(db, limit=60)
        print("translations:", r)
    except Exception as e:
        print("translations EXC:", e)
    finally:
        db.close()

if __name__ == "__main__":
    main()
