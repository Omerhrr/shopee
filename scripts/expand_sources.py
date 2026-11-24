"""Probe every still-untried source (status='new'), enable the scrapable ones,
then run their first scrape + translations. Designed to run detached:
    nohup .venv/bin/python3 /home/z/my-project/scripts/expand_sources.py > /tmp/expand.log 2>&1 &
Stages can be selected: probe | scrape | all (default all).
"""
import sys
import time

sys.path.insert(0, "/home/z/my-project/mini-services/api")

from concurrent.futures import ThreadPoolExecutor

from app.database import SessionLocal
from app import models
from app.services.scraper import collect_product_urls, make_client, scrape_source
from app.services.translator import run_pending_translations

STAGE = sys.argv[1] if len(sys.argv) > 1 else "all"
BUDGET = float(sys.argv[2]) if len(sys.argv) > 2 else 1500.0

probe_results = []


def probe(row):
    sid, name, url = row
    try:
        client = make_client()
        urls, drilled = collect_product_urls(client, url, 4)
        client.close()
        probe_results.append((sid, name, url, f"OK links={len(urls)} drilled={drilled}"))
    except Exception as e:
        probe_results.append((sid, name, url, f"FAIL {type(e).__name__}: {str(e)[:70]}"))


def do_probe(db):
    rows = (
        db.query(models.Source.id, models.Source.name, models.Source.url)
        .filter(models.Source.status == "new", models.Source.enabled == False)  # noqa: E712
        .filter(models.Source.paid_membership == False, models.Source.requires_cafe == False)  # noqa: E712
        .all()
    )
    print(f"[probe] {len(rows)} untried sources", flush=True)
    with ThreadPoolExecutor(max_workers=12) as ex:
        list(ex.map(probe, rows))

    ok = [r for r in probe_results if r[3].startswith("OK") and "links=0" not in r[3]]
    nolinks = [r for r in probe_results if r[3].startswith("OK") and "links=0" in r[3]]
    failed = [r for r in probe_results if r[3].startswith("FAIL")]
    print(f"[probe] scrapable={len(ok)} reachable_no_links={len(nolinks)} unreachable={len(failed)}", flush=True)
    for r in ok:
        print(f"  SCRAPABLE [{r[0]}] {r[1][:30]:32} {r[3]}", flush=True)
    for r in nolinks:
        print(f"  NOLINKS   [{r[0]}] {r[1][:30]:32} {r[3]}", flush=True)
    for r in failed:
        print(f"  UNREACH   [{r[0]}] {r[1][:30]:32} {r[3]}", flush=True)

    # enable the scrapable ones
    enabled = 0
    for sid, name, url, msg in ok:
        src = db.query(models.Source).filter(models.Source.id == sid).first()
        if src and not src.enabled:
            src.enabled = True
            src.status = "new"
            enabled += 1
    db.commit()
    print(f"[probe] enabled {enabled} sources", flush=True)


def do_scrape(db):
    rows = db.query(models.Source).filter(models.Source.enabled == True).all()  # noqa: E712
    todo = [s for s in rows if db.query(models.Product).filter(models.Product.source_id == s.id).count() == 0]
    print(f"[scrape] {len(todo)} enabled sources without products", flush=True)
    start = time.time()
    added = 0
    for s in todo:
        if time.time() - start > BUDGET:
            print(f"[scrape] time budget reached, stopping ({len(todo) - todo.index(s)} left)", flush=True)
            break
        t0 = time.time()
        try:
            log = scrape_source(db, s, trigger="manual")
            added += log.new_products or 0
            print(f"  [{s.id:>3}] {s.name[:28]:30} {log.status:>5} +{log.new_products}/~{log.updated_products} "
                  f"({time.time() - t0:.1f}s) {log.message[:90]}", flush=True)
        except Exception as e:
            print(f"  [{s.id:>3}] {s.name[:28]:30} EXC {type(e).__name__}: {str(e)[:90]}", flush=True)
    print(f"[scrape] new products this run: {added}", flush=True)


def do_translations(db):
    r = run_pending_translations(db, limit=200)
    print("[translate]", r, flush=True)


if STAGE in ("probe", "all"):
    db = SessionLocal()
    try:
        do_probe(db)
    finally:
        db.close()

if STAGE in ("scrape", "all"):
    db = SessionLocal()
    try:
        do_scrape(db)
    finally:
        db.close()
    db = SessionLocal()
    try:
        do_translations(db)
    finally:
        db.close()

print("[done]", flush=True)
