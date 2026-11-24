"""Probe which seeded supplier sources are reachable + scrapable (no data saved)."""
import sys
sys.path.insert(0, "/home/z/my-project/mini-services/api")

import httpx
from app.services.scraper import collect_product_urls, make_client

results = []


def probe(row):
    sid, name, url, adapter = row
    try:
        client = make_client()
        urls, drilled = collect_product_urls(client, url, 4)
        client.close()
        results.append((name, url, f"OK links={len(urls)} drilled={drilled}"))
    except Exception as e:
        results.append((name, url, f"FAIL {type(e).__name__}: {str(e)[:60]}"))


if __name__ == "__main__":
    from app.database import SessionLocal
    from app import models

    db = SessionLocal()
    rows = (
        db.query(models.Source.id, models.Source.name, models.Source.url, models.Source.adapter)
        .filter(models.Source.paid_membership == False, models.Source.requires_cafe == False)  # noqa: E712
        .filter(models.Source.status.in_(["new", "error"]))
        .all()
    )
    db.close()
    print(f"probing {len(rows)} sources...")
    from concurrent.futures import ThreadPoolExecutor

    with ThreadPoolExecutor(max_workers=12) as ex:
        list(ex.map(probe, rows))
    ok = [r for r in results if r[2].startswith("OK") and "links=0" not in r[2]]
    reachable_no_links = [r for r in results if r[2].startswith("OK") and "links=0" in r[2]]
    failed = [r for r in results if r[2].startswith("FAIL")]
    print("\n=== SCRAPABLE (found product links) ===")
    for r in ok:
        print(f"  {r[0]}  {r[1]}  {r[2]}")
    print("\n=== reachable but no product links ===")
    for r in reachable_no_links:
        print(f"  {r[0]}  {r[1]}  {r[2]}")
    print(f"\n=== failed ({len(failed)}) ===")
    for r in failed[:20]:
        print(f"  {r[0]}  {r[1]}  {r[2]}")
    print(f"\nSUMMARY scrapable={len(ok)} nolinks={len(reachable_no_links)} failed={len(failed)}")
