"""Rebuild the scraped catalog after a sandbox reset (DB + media were not in git).

Stages, all resumable - re-running the script continues where it left off:
  1. probe every untried source (12 threads), enable the scrapable ones
  2. give enabled sources deep-scrape configs (max_products/max_pages)
  3. scrape passes until no new products or budget is exhausted
  4. translate pending listings (google_free default)

Run detached:
  cd /home/z/my-project && setsid nohup mini-services/api/.venv/bin/python3 \
      scripts/rebuild_catalog.py > /tmp/rebuild.log 2>&1 < /dev/null &
"""
import sys
import time
from concurrent.futures import ThreadPoolExecutor

sys.path.insert(0, "/home/z/my-project/mini-services/api")

from app import models
from app.database import SessionLocal
from app.deps import set_setting
from app.services.scraper import collect_product_urls, make_client, scrape_source
from app.services.translator import run_pending_translations

PASS_BUDGET = 2400.0  # seconds per scrape pass
MAX_PASSES = 4

probe_results = []


def probe(row):
    sid, name, url = row
    try:
        client = make_client()
        urls, drilled = collect_product_urls(client, url, 4)
        client.close()
        probe_results.append((sid, name, url, f"OK links={len(urls)} drilled={drilled}"))
        print(f"  probe [{sid:>3}] {name[:24]:26} OK links={len(urls)}", flush=True)
    except Exception as e:
        probe_results.append((sid, name, url, f"FAIL {type(e).__name__}: {str(e)[:70]}"))
        print(f"  probe [{sid:>3}] {name[:24]:26} FAIL {type(e).__name__}", flush=True)


def do_probe(db):
    rows = (
        db.query(models.Source.id, models.Source.name, models.Source.url)
        .filter(models.Source.status == "new", models.Source.enabled == False)  # noqa: E712
        .filter(models.Source.paid_membership == False, models.Source.requires_cafe == False)  # noqa: E712
        .all()
    )
    print(f"[probe] {len(rows)} untried sources", flush=True)
    t0 = time.time()
    with ThreadPoolExecutor(max_workers=12) as ex:
        list(ex.map(probe, rows))
    print(f"[probe] done in {time.time() - t0:.0f}s", flush=True)

    ok = [r for r in probe_results if r[3].startswith("OK") and "links=0" not in r[3]]
    nolinks = [r for r in probe_results if r[3].startswith("OK") and "links=0" in r[3]]
    failed = [r for r in probe_results if r[3].startswith("FAIL")]
    print(f"[probe] scrapable={len(ok)} reachable_no_links={len(nolinks)} unreachable={len(failed)}", flush=True)
    for r in ok:
        print(f"  SCRAPABLE [{r[0]}] {r[1][:30]:32} {r[3]}", flush=True)

    enabled = 0
    for sid, name, url, msg in ok:
        src = db.query(models.Source).filter(models.Source.id == sid).first()
        if src and not src.enabled:
            src.enabled = True
            src.status = "new"
            src.config = {"max_products": 400, "max_pages": 15}
            enabled += 1
    set_setting(db, "scrape_max_products_per_run", 400)
    db.commit()
    print(f"[probe] enabled {enabled} sources (config: max_products=400, max_pages=15)", flush=True)


def do_scrape_pass(db, pass_no: int) -> int:
    rows = db.query(models.Source).filter(models.Source.enabled == True).all()  # noqa: E712
    todo = [s for s in rows if db.query(models.Product).filter(models.Product.source_id == s.id).count() < 400]
    print(f"[scrape pass {pass_no}] {len(todo)} enabled sources below cap", flush=True)
    start = time.time()
    added = 0
    for s in todo:
        if time.time() - start > PASS_BUDGET:
            print(f"[scrape pass {pass_no}] budget reached, stopping ({len(todo) - todo.index(s)} left)", flush=True)
            break
        t0 = time.time()
        try:
            log = scrape_source(db, s, trigger="manual")
            added += log.new_products or 0
            print(
                f"  [{s.id:>3}] {s.name[:28]:30} {log.status:>5} +{log.new_products}/~{log.updated_products} "
                f"({time.time() - t0:.1f}s) {log.message[:90]}",
                flush=True,
            )
        except Exception as e:
            print(f"  [{s.id:>3}] {s.name[:28]:30} EXC {type(e).__name__}: {str(e)[:90]}", flush=True)
    print(f"[scrape pass {pass_no}] new products: {added}", flush=True)
    return added


def do_translations(db, rounds: int = 6):
    total = 0
    for i in range(rounds):
        r = run_pending_translations(db, limit=300)
        done = r.get("translated", 0) if isinstance(r, dict) else 0
        total += done
        if not done:
            break
    print(f"[translate] translated {total} listings", flush=True)


db = SessionLocal()
try:
    if db.query(models.Source).filter(models.Source.status == "new").count() > 0:
        do_probe(db)
    for p in range(1, MAX_PASSES + 1):
        if do_scrape_pass(db, p) == 0:
            break
    do_translations(db)
    n = db.query(models.Product).count()
    print(f"[done] catalog now holds {n} products", flush=True)
finally:
    db.close()
