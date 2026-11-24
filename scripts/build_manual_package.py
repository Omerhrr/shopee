"""Build a single ready-to-send ZIP so a colleague can post the scraped
catalog to Shopee (Korea Seller Center) manually, before the Open API is wired.

Package layout:
  shopee_manual_listing_package.zip
    |- README.txt                  EN + KR instructions (real product counts)
    |- shopee_mass_upload.csv      one row per product, ordered by Item SKU
    |- images/
       |- SP-000053_1.jpg          main image (matched to the row by Item SKU)
       |- SP-000053_2.jpg          second image, ...

The CSV is downloaded from the tested admin export endpoint (single source of
truth for which products/rows are included); images are read straight from the
local media store, so rows and files always stay matched by Item SKU.
"""
import csv
import io
import json
import os
import sqlite3
import urllib.request
from datetime import date
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZIP_STORED, ZipFile

ROOT = Path("/home/z/my-project")
API = "http://127.0.0.1:8000"
DB_PATH = ROOT / "mini-services/api/data/shopee.db"
MEDIA_DIR = ROOT / "mini-services/api/media"
OUT = ROOT / "download/shopee_manual_listing_package.zip"
MAX_IMAGES = 5  # matches the 5 image URL columns in the CSV
ALLOWED_EXT = {".jpg", ".jpeg", ".png", ".webp"}

# ---- 1. fetch the export CSV (already filters: published, enabled source, has image, price > 0) ----
ADMIN_EMAIL = os.getenv("SHOPEE_ADMIN_EMAIL", "admin@shopee.kr")
ADMIN_PASSWORD = os.getenv("SHOPEE_ADMIN_PASSWORD", "admin1234")
login_req = urllib.request.Request(
    API + "/api/auth/login",
    data=json.dumps({"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}).encode(),
    headers={"Content-Type": "application/json"},
)
token = json.load(urllib.request.urlopen(login_req, timeout=30))["access_token"]
csv_req = urllib.request.Request(
    API + "/api/admin/export/shopee.csv", headers={"Authorization": "Bearer " + token}
)
csv_bytes = urllib.request.urlopen(csv_req, timeout=180).read()
rows = list(csv.DictReader(io.StringIO(csv_bytes.decode("utf-8-sig"))))
print(f"CSV rows (products): {len(rows)}")

# ---- 2. map Item SKU -> local image files (read-only DB access) ----
db = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
db.row_factory = sqlite3.Row

def images_for_pid(pid: int) -> list[Path]:
    row = db.execute("SELECT images FROM products WHERE id = ?", (pid,)).fetchone()
    if not row or not row["images"]:
        return []
    try:
        entries = json.loads(row["images"])
    except Exception:
        return []
    out: list[Path] = []
    seen: set[str] = set()
    for e in entries or []:
        if not isinstance(e, str) or not e.strip():
            continue
        u = e.strip()
        if u.startswith(("http://", "https://")):
            continue  # remote-only image: nothing local to zip
        rel = u.lstrip("/")
        if rel.startswith("media/"):
            rel = rel[len("media/"):]
        p = MEDIA_DIR / rel
        rp = str(p.resolve())
        if rp in seen:
            continue
        seen.add(rp)
        if p.is_file() and p.stat().st_size > 512 and p.suffix.lower() in ALLOWED_EXT:
            out.append(p)
        if len(out) >= MAX_IMAGES:
            break
    return out

sku_files: dict[str, list[Path]] = {}
missing: list[str] = []
total_bytes = 0
for r in rows:
    sku = r["Item SKU"]
    pid = int(sku.split("-")[1])
    files = images_for_pid(pid)
    if not files:
        missing.append(sku)
    sku_files[sku] = files
    total_bytes += sum(f.stat().st_size for f in files)
print(f"products with local images: {len(rows) - len(missing)}/{len(rows)}")
print(f"total image bytes: {total_bytes / 1e6:.1f} MB ({sum(len(v) for v in sku_files.values())} files)")

# ---- 3. write the package ----
OUT.parent.mkdir(parents=True, exist_ok=True)
today = date.today().isoformat()
n = len(rows)

readme = f"""SHOPEE LISTING PACKAGE - for manual posting
============================================
Generated: {today}
Products: {n} (one row per product in shopee_mass_upload.csv, ordered by Item SKU)
Source:   Korean wholesale sites, scraped into our own catalog

WHAT'S INSIDE
-------------
- shopee_mass_upload.csv ... one row = one product. Columns: Category ID, Product Name,
  Description, Price, Stock, Item SKU, Logistics, Product Image URL 1-5,
  Weight (g), Package Length/Width/Height (cm).
- images/ .................. product photos named by Item SKU:
  SP-000053_1.jpg = MAIN (first) image, SP-000053_2.jpg = second image, ... (up to {MAX_IMAGES} per product).
- README.txt ............... this file.

HOW TO POST (Shopee Seller Center - seller.shopee.kr)
-----------------------------------------------------
1. Sign in to Seller Center.
2. Fastest way: Products > Add Products > Mass Upload. Download the latest official
   template there, paste our rows into it (keep the column order), then fill the
   "Category ID" column using the template's category list (closest match per product).
3. Or post one by one: copy Product Name / Description / Price from the CSV row and
   attach the images whose filename starts with that row's Item SKU.
4. Keep the Item SKU exactly as-is (SP-xxxxxx). It keeps rows and images matched, and
   lets us match future Shopee orders back to our own catalog.

PRICES
------
- Prices are in KRW (Korean won). If the shop lists in USD, convert at your working
  rate (e.g. 1,350 KRW = 1 USD) - or ask us to regenerate the file in USD.

NOTES
-----
- "Category ID" is blank on purpose: Shopee category IDs differ per market, so pick
  the closest category in Seller Center.
- Stock / weight / package size are safe defaults - adjust per product if you know better.
- The "Product Image URL" columns point at our own server and may not open in your
  browser - use the files in images/ instead.
- Only list products you are authorized to resell; photos and brands belong to the
  original suppliers.

----------------------------------------------------------------------------------------
(한국어 안내)

쇼피 상품 등록 패키지 - 수동 등록용
생성일: {today} / 상품 수: {n}개 (CSV 한 줄 = 상품 1개, SKU 순서)

파일 구성
- shopee_mass_upload.csv : 상품 정보 (상품명 / 설명 / 가격 / 재고 / Item SKU / 이미지 URL / 중량·크기)
- images/ 폴더           : 상품별 사진. 파일명이 SKU와 연결됩니다.
  예) SP-000053_1.jpg = 대표 이미지, SP-000053_2.jpg = 두 번째 이미지 (상품당 최대 {MAX_IMAGES}장)

등록 방법 (셀러센터 seller.shopee.kr)
1. 셀러센터 로그인
2. 빠른 방법: 상품 등록 > 대량 업로드(Mass Upload)에서 최신 공식 템플릿을 내려받아
   CSV 내용을 붙여넣고, "Category ID"는 템플릿의 카테고리 목록에서 가장 가까운 것으로 입력
3. 한 건씩 등록할 경우: CSV의 상품명/설명/가격을 복사하고 images/에서 같은 SKU로 시작하는
   이미지를 첨부 (_1 파일이 대표 이미지)
4. Item SKU(SP-xxxxxx)는 절대 수정하지 마세요 - 이미지·주문 매칭의 기준입니다.

참고
- 가격은 원(KRW) 기준입니다. USD로 등록 시 환율로 변환하거나 요청하시면 USD 버전을 만들어 드립니다.
- Category ID는 비워두었습니다. 셀러센터에서 시장별 카테고리를 선택하세요.
- 재고/중량/사이즈는 안전한 기본값입니다. 실제 정보를 알면 수정하세요.
- CSV의 이미지 URL은 우리 서버 주소라 브라우저에서 열리지 않을 수 있습니다. images/ 폴더의 파일을 사용하세요.
- 판매 승인을 받은 상품만 등록하세요. 이미지·브랜드 권리는 원래 공급사에 있습니다.
"""

with ZipFile(OUT, "w") as z:
    z.writestr("README.txt", readme, compress_type=ZIP_DEFLATED)
    z.writestr("shopee_mass_upload.csv", csv_bytes, compress_type=ZIP_DEFLATED)
    added = 0
    for sku in [r["Item SKU"] for r in rows]:
        for i, f in enumerate(sku_files[sku], start=1):
            ext = ".jpg" if f.suffix.lower() == ".jpeg" else f.suffix.lower()
            z.write(f, f"images/{sku}_{i}{ext}", compress_type=ZIP_STORED)
            added += 1
print(f"zip written: {OUT} ({OUT.stat().st_size / 1e6:.1f} MB, {added} images)")

# ---- 4. verify: reopen the package and cross-check ----
with ZipFile(OUT) as z:
    assert z.testzip() is None, "zip integrity check failed"
    names = z.namelist()
    csv_check = list(csv.DictReader(io.StringIO(z.read("shopee_mass_upload.csv").decode("utf-8-sig"))))
    prefixes = {n[len("images/"):].rsplit("_", 1)[0] for n in names if n.startswith("images/")}
    lost = [r["Item SKU"] for r in csv_check if r["Item SKU"] not in prefixes]
    print("VERIFY zip files:", len(names))
    print("VERIFY csv rows inside zip:", len(csv_check))
    print("VERIFY products missing images:", len(lost), lost[:5] if lost else "")
    print("VERIFY integrity: OK" if not lost else "VERIFY FAILED: rows without images")
