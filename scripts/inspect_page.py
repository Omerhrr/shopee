"""Inspect a godomall/cafe24 product page for title/price/image selectors."""
import re
import sys

sys.path.insert(0, "/home/z/my-project/mini-services/api")
from app.services.scraper import collect_product_urls, fetch_html, make_client  # noqa: E402

c = make_client()
urls, _ = collect_product_urls(c, "http://babonara.co.kr/shop/main/index.php", 3)
html = fetch_html(c, urls[0])
print("URL:", urls[0], "| len:", len(html))

TITLE_PATS = [
    (r"<h1[^>]*>(.{5,160}?)</h1>", re.S),
    (r'class="goods_name[^"]*"[^>]*>(.{5,160}?)<', 0),
    (r'id="goods_name"[^>]*>(.{5,160}?)<', 0),
    (r"<title>(.{5,160}?)</title>", 0),
    (r'itemprop="name"[^>]*>(.{5,160}?)<', 0),
    (r'class="prd_name[^"]*"[^>]*>(.{5,160}?)<', 0),
]
for pat, flags in TITLE_PATS:
    m = re.findall(pat, html, flags)
    if m:
        print(f"TITLE {pat[:36]}: {[re.sub(r'\\s+', ' ', x).strip()[:70] for x in m[:3]]}")

PRICE_PATS = [
    r'id="goods_price"[^>]*>(.{2,80}?)<',
    r'class="price[^"]*"[^>]*>(.{2,80}?)<',
    r"goods_price\D{0,20}([\d,]{4,})",
    r"product_price\D{0,20}([\d,]{4,})",
]
for pat in PRICE_PATS:
    m = re.findall(pat, html)
    if m:
        print(f"PRICE {pat[:40]}: {m[:5]}")

IMG_PATS = [
    r'og:image" content="([^"]+)"',
    r'class="thumbnail[^"]*"[^>]*<img[^>]*src="([^"]+)"',
    r"<img[^>]+src=\"([^\"]*/goods/[^\"]+)\"",
    r"<img[^>]+src=\"([^\"]*goods_[^\"]+)\"",
]
for pat in IMG_PATS:
    m = re.findall(pat, html)
    if m:
        print(f"IMG {pat[:40]}: {[x[:90] for x in m[:3]]}")

DESC_PATS = [r'id="goods_summary"[^>]*>(.{5,200}?)<', r'og:description" content="([^"]+)"']
for pat in DESC_PATS:
    m = re.findall(pat, html)
    if m:
        print(f"DESC {pat[:40]}: {[x[:90] for x in m[:2]]}")

c.close()
