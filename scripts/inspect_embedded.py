"""Look for embedded product data (JS vars / JSON) in a godomall page."""
import re
import sys

sys.path.insert(0, "/home/z/my-project/mini-services/api")
from app.services.scraper import fetch_html, make_client  # noqa: E402

c = make_client()
html = fetch_html(c, "http://babonara.co.kr/shop/goods/goods_view.php?goodsno=18&category=")
c.close()

for kw in ["goods_price", "goods_name", "price", "원", "selling_price", "goods_info", "goodsno"]:
    idxs = [m.start() for m in re.finditer(kw, html)][:6]
    for i in idxs[:3]:
        snippet = re.sub(r"\s+", " ", html[max(0, i - 60):i + 140])
        print(f"[{kw}] …{snippet}…")
    print("-" * 60)
