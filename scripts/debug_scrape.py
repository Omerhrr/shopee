"""Debug why specific source detail pages fail to parse."""
import sys
sys.path.insert(0, "/home/z/my-project/mini-services/api")

import re
from app.database import SessionLocal
from app import models
from app.services.scraper import (
    collect_product_urls, fetch_html, extract_product, parse_price_int, make_client
)

db = SessionLocal()
names = sys.argv[1:] or ["가방쟁이", "소소홈", "트라이코지"]
for name in names:
    s = db.query(models.Source).filter(models.Source.name == name).first()
    if not s:
        print("no source", name)
        continue
    print(f"\n===== {s.name} :: {s.url} =====")
    try:
        client = make_client()
        urls, drilled = collect_product_urls(client, (s.config or {}).get("listing_url") or s.url, 3)
        print(f"links: {len(urls)} drilled={drilled}")
        for u in urls[:2]:
            try:
                html = fetch_html(client, u)
                item = extract_product(html, u)
                if item:
                    print(f"  OK: {item['title'][:50]!r} price={item['price']} images={len(item.get('images', []))}")
                else:
                    title_m = re.search(r"<title>(.*?)</title>", html, re.S | re.I)
                    print(f"  PARSE-FAIL url={u[:90]}")
                    print(f"    page title: {(title_m.group(1) if title_m else '?')[:70]!r} len={len(html)}")
                    print(f"    price candidates: {parse_price_int(html)}")
                    print(f"    og:title: {bool(html.find('og:title'))}, ld+json: {html.count('ld+json')}")
            except Exception as e:
                print(f"  FETCH-FAIL {type(e).__name__} {str(e)[:80]}")
        client.close()
    except Exception as e:
        print(f"LIST-FAIL {type(e).__name__} {str(e)[:120]}")
db.close()
