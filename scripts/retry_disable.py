"""Retry failed sources once; disable those that still fail; print summary."""
import sys
import time

sys.path.insert(0, "/home/z/my-project/mini-services/api")

from app.database import SessionLocal
from app import models
from app.services.scraper import scrape_source

def main():
    db = SessionLocal()
    try:
        rows = (
            db.query(models.Source)
            .filter(models.Source.enabled == True)  # noqa: E712
            .filter(models.Source.status == "error")
            .all()
        )
        print(f"retrying {len(rows)} failed sources...")
        for s in rows:
            time.sleep(0.5)
            try:
                log = scrape_source(db, s, trigger="manual")
                has = db.query(models.Product).filter(models.Product.source_id == s.id).count()
                if log.status != "ok" or has == 0:
                    s.enabled = False
                    print(f"[{s.id}] {s.name}: STILL FAILING -> disabled | {log.message[:90]}")
                else:
                    print(f"[{s.id}] {s.name}: recovered +{log.new_products}")
            except Exception as e:
                s.enabled = False
                print(f"[{s.id}] {s.name}: EXC {type(e).__name__} -> disabled")
            db.commit()
        enabled = db.query(models.Source).filter(models.Source.enabled == True).count()  # noqa: E712
        total = db.query(models.Product).count()
        real = db.query(models.Product).filter(models.Product.is_manual == False).count()  # noqa: E712
        print(f"\nenabled sources: {enabled} | total products: {total} (scraped: {real})")
    finally:
        db.close()

if __name__ == "__main__":
    main()
