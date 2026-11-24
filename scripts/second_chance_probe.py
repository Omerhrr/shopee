"""Second-chance probe for sources marked 'no product links': try common Korean
mall listing paths (cafe24 / godomall / makeshop), generated pagination, and the
widened detail-link patterns. Sources where we find product links get configured
(listing_url) and enabled for the next scrape run."""
import sys

sys.path.insert(0, "/home/z/my-project/mini-services/api")

from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urlsplit

from app.database import SessionLocal
from app import models
from app.services.scraper import (
    collect_product_urls,
    extract_listing_urls,
    fetch_html,
    make_client,
)

CANDIDATE_PATHS = [
    "",
    "/shop/goods/goods_list.php",
    "/shop/goods/goods_list.php?page=1",
    "/goods/goods_list.php",
    "/shop/list.php",
    "/product/list.html",
    "/shop/shoplist.html",
    "/sub/list.html",
    "/new_product/list.html",
]


def try_site(row):
    sid, name, url = row
    if not url or not url.startswith("http"):
        return (sid, name, url, None, "no url")
    base = f"{urlsplit(url).scheme}://{urlsplit(url).netloc}"
    client = make_client()
    best = None
    err = ""
    for path in CANDIDATE_PATHS:
        cand = base + path
        try:
            html = fetch_html(client, cand)
        except Exception as e:
            err = f"{type(e).__name__}"
            continue
        try:
            d, c = extract_listing_urls(html, cand, 60)
        except Exception:
            continue
        if d:
            best = (cand, d)
            break
    if not best:
        # last resort: let the full collector try (pagination walk + drilldown)
        try:
            urls, drilled = collect_product_urls(client, url, 40, max_pages=4)
            if urls:
                best = (url, urls)
        except Exception as e:
            err = f"{type(e).__name__}: {str(e)[:60]}"
    client.close()
    if best:
        return (sid, name, best[0], best[1][:5], "")
    return (sid, name, url, None, err or "no product links")


if __name__ == "__main__":
    db = SessionLocal()
    try:
        rows = (
            db.query(models.Source.id, models.Source.name, models.Source.url)
            .filter(models.Source.status == "error", models.Source.enabled == False)  # noqa: E712
            .filter(models.Source.last_error.like("%JavaScript-rendered%custom layout%"))
            .all()
        )
        print(f"second-chance probing {len(rows)} sources...", flush=True)
        found = []
        with ThreadPoolExecutor(max_workers=10) as ex:
            for sid, name, listing, sample, err in ex.map(try_site, rows):
                if sample:
                    found.append((sid, name, listing, sample))
                    print(f"  FOUND   [{sid:>3}] {name[:28]:30} listing={listing[:70]}", flush=True)
                    for u in sample:
                        print(f"            {u[:100]}", flush=True)
                else:
                    print(f"  nothing [{sid:>3}] {name[:28]:30} {err}", flush=True)

        n = 0
        for sid, name, listing, sample in found:
            s = db.query(models.Source).filter(models.Source.id == sid).first()
            cfg = dict(s.config or {})
            cfg["listing_url"] = listing
            cfg.setdefault("max_products", 2000)
            cfg.setdefault("max_pages", 20)
            s.config = cfg
            s.enabled = True
            s.status = "new"
            n += 1
        db.commit()
        print(f"[done] configured + enabled {n} sources", flush=True)
    finally:
        db.close()
