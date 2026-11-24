"""Parse the uploaded Korean wholesale-sites Excel into seed JSON for the backend."""
import json
import re
from openpyxl import load_workbook

SRC = "/home/z/my-project/upload/국내도매사이트리스트-1.xlsx"
OUT = "/home/z/my-project/scripts/sources.json"

wb = load_workbook(SRC, read_only=True, data_only=True)
ws = wb.active

rows = list(ws.iter_rows(values_only=True))
header = rows[0]
print("HEADER:", header)

def s(v):
    if v is None:
        return ""
    return str(v).strip()

PAID_PAT = re.compile(r"유료|계약금|회원가입비|결제")

sources = []
seen_names = set()
for i, row in enumerate(rows[1:], start=1):
    vals = (list(row) + [None]*8)[:8]
    # Sheet layout: 사이트명, 사이트URL, 카테고리, 상품, 이미지제공여부, 위탁배송, 연락처, 비고
    if s(vals[0]).isdigit():  # some exports include a numeric index first
        vals = vals[1:] + [None]
    name, url, category, products, img, dropship, contact, note = vals
    name = s(name)
    if not name or name in seen_names:
        continue
    seen_names.add(name)
    url = s(url)
    note = s(note)
    img = s(img)
    paid = bool(PAID_PAT.search(note)) or bool(PAID_PAT.search(img))
    requires_cafe = "naver.com" in url.lower()
    no_site = (not url) or url == "사이트X"
    image_ok = img.startswith("O")
    sources.append({
        "row_index": i,
        "name": name,
        "url": "" if no_site else url,
        "category_hint": s(category),
        "products_hint": s(products),
        "image_provided": image_ok,
        "dropship_possible": s(dropship) == "가능",
        "contact": s(contact),
        "notes": note,
        "paid_membership": paid,
        "requires_cafe": requires_cafe,
        "active": False,  # disabled by default; admin enables + configures adapters
    })

print(f"parsed {len(sources)} sources")
with open(OUT, "w", encoding="utf-8") as f:
    json.dump(sources, f, ensure_ascii=False, indent=2)

# quick stats
cats = {}
for sc in sources:
    cats[sc["category_hint"]] = cats.get(sc["category_hint"], 0) + 1
print("categories:", json.dumps(cats, ensure_ascii=False))
print("paid:", sum(1 for x in sources if x["paid_membership"]),
      "| cafe:", sum(1 for x in sources if x["requires_cafe"]),
      "| no url:", sum(1 for x in sources if not x["url"]))
