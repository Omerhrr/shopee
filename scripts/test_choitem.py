"""Try generic extraction against choitemb2b detail pages."""
import sys

sys.path.insert(0, "/home/z/my-project/mini-services/api")
from app.services.scraper import collect_product_urls, extract_product, fetch_html, make_client  # noqa: E402

c = make_client()
urls, drilled = collect_product_urls(c, "http://choitemb2b.com/", 6)
print("detail urls:", len(urls), "drilled:", drilled)
for u in urls[:4]:
    try:
        html = fetch_html(c, u)
        item = extract_product(html, u)
        print("-", u[:90])
        if item:
            print("   title:", (item.get("title") or "")[:70])
            print("   price:", item.get("price"), "| img:", (item.get("image") or "")[:80])
        else:
            print("   -> no data")
    except Exception as e:
        print("-", u[:80], "ERR:", str(e)[:100])
c.close()
