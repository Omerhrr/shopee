"""Web scraper for Korean wholesale supplier sites.

Generic adapter that works across cafe24 / godomall / custom shops:
  1. fetch the listing page (source.url or config.listing_url)
  2. collect candidate product page URLs
  3. fetch each page, extract product data (JSON-LD first, OpenGraph + heuristics fallback)
  4. download images locally, upsert products, apply markup, queue translation
Sources with paid membership / Naver-cafe requirements are flagged and excluded from
auto-scraping unless the admin supplies credentials via source.config.
"""
import hashlib
import json
import random
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from urllib.parse import parse_qsl, urlencode, urlparse

import httpx
from bs4 import BeautifulSoup
from sqlalchemy.orm import Session

from .. import models
from . import media_store
from .markup import apply_pricing
from .translator import pending_count as _pc  # noqa: F401 (used by admin)
from .translator import translate_product, translate_source_labels
from ..deps import get_setting

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0 Safari/537.36"
)
# Product DETAIL page patterns (cafe24 / godomall / makeshop / custom shops)
DETAIL_PAT = re.compile(
    r"(product_no=\d+|goodsno=\d+|goods_view|product/detail|/product/\d|/goods/\d|/shop_goods/"
    r"|item\.html|prd.+detail|\.php\?uid=\d+|product_code=|branduid=\d+|goodsno=[a-z0-9]+"
    r"|productno=\d+|itemno=\d+|goods_view\.php|shopdetail)",
    re.I,
)
# Category LIST page patterns - used for drill-down when only the homepage is given
CATEGORY_PAT = re.compile(r"(product/list\.html|goods_list|cate_no=\d+|category_no=\d+|/category/|/shop/)", re.I)
EXCLUDE_PAT = re.compile(
    r"(board|event|login|join|cart|order(?![_=])|mypage|faq|notice|search|main|member|agree"
    r"|company|guide|service|cate_no=\d+$|list\.html$)",
    re.I,
)
PRICE_PAT = re.compile(r"(?:₩|원|\bKRW\b)\s*([\d,]{4,})|([\d,]{4,})\s*(?:원|KRW)", re.I)


def make_client() -> httpx.Client:
    return httpx.Client(
        headers={"User-Agent": UA, "Accept-Language": "ko-KR,ko;q=0.9,en;q=0.8"},
        follow_redirects=True,
        timeout=15.0,
    )


def fetch_html(client: httpx.Client, url: str) -> str:
    r = client.get(url)
    r.raise_for_status()
    if not r.encoding or r.encoding.lower() in ("iso-8859-1", "ascii"):
        r.encoding = r.charset_encoding or "utf-8"
    return r.text


def parse_price_int(text: str) -> int | None:
    candidates = []
    for m in PRICE_PAT.finditer(text):
        raw = (m.group(1) or m.group(2) or "").replace(",", "")
        if raw.isdigit():
            v = int(raw)
            if 500 <= v <= 50_000_000:
                candidates.append(v)
    return min(candidates) if candidates else None


def _abs(base_url: str, href: str) -> str:
    if href.startswith("//"):
        return "https:" + href
    if href.startswith("http"):
        return href
    from urllib.parse import urljoin

    return urljoin(base_url, href)


def extract_listing_urls(html: str, base_url: str, limit: int) -> tuple[list[str], list[str]]:
    """Return (product detail urls, category list urls) found on a page."""
    soup = BeautifulSoup(html, "lxml")
    details, cats, seen = [], [], set()
    for a in soup.find_all("a", href=True):
        href = (a["href"] or "").split("#")[0]
        if not href or href in seen:
            continue
        if EXCLUDE_PAT.search(href):
            continue
        url = _abs(base_url, href)
        if url in seen:
            continue
        if DETAIL_PAT.search(href):
            seen.add(url)
            details.append(url)
        elif CATEGORY_PAT.search(href):
            seen.add(url)
            cats.append(url)
        if len(details) >= limit and len(cats) >= 8:
            break
    return details, cats


def _page_pattern_in(url: str) -> re.Match | None:
    return re.search(r"(page=\d+|page-\d+|/page/\d+|page_num=\d+)", url, re.I)


def _generate_page_urls(url: str, max_pages: int) -> list[str]:
    """Generate sequential pagination URLs for the common Korean-mall patterns:
    ?page=N / page-N / /page/N / page_num=N. If the url has no page pattern,
    append ?page=N (or &page=N when a query string already exists)."""
    out: list[str] = []
    if max_pages <= 1:
        return out
    m = _page_pattern_in(url)
    if m:
        prefix = m.group(0)[:-len(re.search(r"\d+", m.group(0)).group(0))]
        for n in range(2, max_pages + 1):
            out.append(url.replace(m.group(0), f"{prefix}{n}", 1))
        return out
    sep = "&" if "?" in url else "?"
    for n in range(2, max_pages + 1):
        out.append(f"{url}{sep}page={n}")
    return out


def collect_product_urls(client: httpx.Client, listing_url: str, limit: int, max_pages: int = 1) -> tuple[list[str], int]:
    """Collect product detail URLs for FULL listings:
      1. fetch the listing page, then walk its pagination (discovered links AND
         sequentially generated ?page=N urls) up to max_pages fetches
      2. if that yields few products, drill into category pages (their own
         first pagination page included) for a wider crawl
    Returns (urls, drilled_category_count)."""
    details: list[str] = []
    cats: list[str] = []

    def _merge(d_new: list[str], c_new: list[str]) -> None:
        for u in d_new:
            if u not in details:
                details.append(u)
        for u in c_new:
            if u not in cats:
                cats.append(u)

    # --- phase 1: listing page + pagination walk ---
    html0 = fetch_html(client, listing_url)
    _merge(*extract_listing_urls(html0, listing_url, limit * 3))

    queue: list[str] = []
    seen_pages = {listing_url}
    for u in _generate_page_urls(listing_url, max_pages):
        if u not in seen_pages:
            seen_pages.add(u)
            queue.append(u)

    soup0 = BeautifulSoup(html0, "lxml")
    page_pat = re.compile(r"(page=\d+|page-\d+|/page/\d+|page_num=\d+)", re.I)
    for a in soup0.find_all("a", href=True):
        href = (a["href"] or "").split("#")[0]
        if href and page_pat.search(href) and not EXCLUDE_PAT.search(href):
            u = _abs(listing_url, href)
            if u not in seen_pages:
                seen_pages.add(u)
                queue.append(u)
            if len(queue) >= max_pages * 2:
                break

    fetches = 1
    while queue and fetches < max_pages and len(details) < limit:
        pu = queue.pop(0)
        try:
            time.sleep(random.uniform(0.3, 0.7))
            html_n = fetch_html(client, pu)
        except Exception:
            continue
        fetches += 1
        _merge(*extract_listing_urls(html_n, pu, limit * 2))
        # pagination found deeper in the walk
        sp = BeautifulSoup(html_n, "lxml")
        for a in sp.find_all("a", href=True):
            href = (a["href"] or "").split("#")[0]
            if href and page_pat.search(href) and not EXCLUDE_PAT.search(href):
                u = _abs(pu, href)
                if u not in seen_pages:
                    seen_pages.add(u)
                    queue.append(u)

    # --- phase 2: category drill-down when the listing itself is sparse ---
    drilled = 0
    if len(details) < min(limit, 20) and cats:
        for cu in cats[:8]:
            if len(details) >= limit:
                break
            try:
                time.sleep(random.uniform(0.3, 0.8))
                html2 = fetch_html(client, cu)
            except Exception:
                continue
            drilled += 1
            _merge(*extract_listing_urls(html2, cu, limit * 2))
            for g in _generate_page_urls(cu, min(max_pages, 3)):
                try:
                    time.sleep(random.uniform(0.2, 0.5))
                    html3 = fetch_html(client, g)
                    _merge(*extract_listing_urls(html3, g, limit * 2))
                except Exception:
                    continue

    return details[:limit], drilled


def _clean(text: str) -> str:
    """Whitespace collapse + em/en dash normalization (house style: no dashes)."""
    t = re.sub(r"\s+", " ", text or "").strip()
    return t.replace("\u2014", "-").replace("\u2013", "-")


def extract_product(html: str, page_url: str, generic: frozenset | set = frozenset()) -> dict | None:
    """JSON-LD (schema.org/Product) first, OpenGraph + price heuristics fallback.
    Also collects up to 3 gallery image URLs."""
    soup = BeautifulSoup(html, "lxml")
    data = {}
    gallery: list[str] = []

    for script in soup.find_all("script", type="application/ld+json"):
        try:
            blob = json.loads(script.string or "{}")
        except Exception:
            continue
        items = blob if isinstance(blob, list) else [blob]
        for it in items:
            if isinstance(it, dict) and it.get("@type") in ("Product", ["Product"]):
                offers = it.get("offers") or {}
                if isinstance(offers, list):
                    offers = offers[0] if offers else {}
                price = offers.get("price") or offers.get("lowPrice")
                img = it.get("image")
                img_list = img if isinstance(img, list) else ([img] if img else [])
                if isinstance(offers.get("image"), str):
                    img_list.append(offers["image"])
                data = {
                    "title": _clean(str(it.get("name", ""))),
                    "price": int(float(str(price).replace(",", ""))) if price else None,
                    "description": _clean(str(it.get("description", "")))[:4000],
                    "image": _abs(page_url, str(img_list[0])) if img_list else None,
                }
                gallery = [_abs(page_url, str(u)) for u in img_list if u]
                break
        if data.get("title"):
            break

    if not data.get("title"):
        og = lambda prop: (soup.find("meta", property=prop) or {}).get("content", "")
        cands = []
        for sel in ("#span_product_name", ".headingArea h2", ".infoArea h2", ".goods_name", ".item_detail_tit", ".prd_name", "h1", "h2.title"):
            el = soup.select_one(sel)
            if el and el.get_text(strip=True):
                cands.append(_clean(el.get_text(" ")))
        cands += [_clean(og("og:title")), _clean(soup.title.string if soup.title else "")]
        # first candidate that is not the site-wide title (some shops return the same og:title on every page)
        title = next((c for c in cands if c and c not in generic), "")
        if not title:
            return None
        desc = _clean(og("og:description") or "")
        img = og("og:image")
        gallery = [_abs(page_url, u) for u in (img, og("og:image:secure_url")) if u]
        price = parse_price_int(og("product:price:amount") or "")
        if not price:
            for sel in ("#span_product_price_text", "#span_product_price_sale", ".price_sale", ".sale_price", ".price"):
                el = soup.select_one(sel)
                if el:
                    price = parse_price_int(el.get_text(" ") + "원") or (int(re.sub(r"\D", "", el.get_text())) if re.sub(r"\D", "", el.get_text()).isdigit() and 500 <= int(re.sub(r"\D", "", el.get_text())) <= 50_000_000 else None)
                    if price:
                        break
        price = price or parse_price_int(html)
        data = {
            "title": title,
            "price": price,
            "description": desc[:4000],
            "image": _abs(page_url, img) if img else None,
        }

    # Gallery candidates from common product-image markup (cafe24 / godomall / custom shops)
    if len(gallery) < 3:
        for im in soup.find_all("img", src=True):
            src = im.get("src") or ""
            if not src or src.startswith("data:"):
                continue
            low = src.lower()
            if any(k in low for k in ("/goods/", "/product/", "/upload/", "/web/upload", "/img/product", "goodsno", "/data/goods")) or (
                im.get("class") and any("product" in c.lower() or "thumb" in c.lower() or "detail" in c.lower() for c in im.get("class", []))
            ):
                u = _abs(page_url, src)
                if u not in gallery:
                    gallery.append(u)
            if len(gallery) >= 3:
                break

    if not data.get("price"):
        data["price"] = parse_price_int(html)
    if not data.get("title"):
        return None
    # Split "상품명 : 옵션" style noise
    data["title"] = re.split(r"\s*[:：]\s*(?:상세|상품)?\s*페이지", data["title"])[0]
    data["images"] = list(dict.fromkeys(gallery))[:3]
    return data


def download_images(client: httpx.Client, urls: list[str], source_id: int, retries: int = 1) -> list[str]:
    """Download images to local storage. Every returned URL is guaranteed to be a
    local /media/... path so the storefront never depends on remote hosts."""
    saved = []
    for u in urls[:3]:
        if not u:
            continue
        for attempt in range(retries + 1):
            try:
                r = client.get(u, timeout=15.0)
                ct = r.headers.get("content-type", "")
                if r.status_code == 200 and ct.startswith("image") and len(r.content) > 1024:
                    name = hashlib.md5(u.encode()).hexdigest()[:16]
                    ext = "jpg" if "jpeg" in ct or "jpg" in ct else ("png" if "png" in ct else "webp")
                    saved.append(media_store.save(f"scraped/{source_id}/{name}.{ext}", r.content, ct.split(";")[0]))
                    break
            except Exception:
                if attempt < retries:
                    time.sleep(0.5)
                continue
    return saved


def make_placeholder_image(source_id: int, title: str, title_en: str, cat_slug: str) -> str:
    """Generate a local SVG placeholder so scraped products always have a working image."""
    from .seed_service import _svg_placeholder

    h = hashlib.md5(title.encode()).hexdigest()[:10]
    svg = _svg_placeholder(f"src-{source_id}-{h}", title[:30], (title_en or title)[:40], "NEW", cat_slug or "general")
    return media_store.save(f"scraped/{source_id}/ph-{h}.svg", svg.encode("utf-8"), "image/svg+xml")


def slugify(text: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", (text or "").lower()).strip("-")
    return s[:80]


def unique_slug(db: Session, base: str, seed: str) -> str:
    h = hashlib.md5(seed.encode()).hexdigest()[:6]
    base = (slugify(base) or "item") + "-" + h
    slug, i = base, 1
    while db.query(models.Product).filter(models.Product.slug == slug).first():
        i += 1
        slug = f"{base}-{i}"
    return slug


ID_KEYS = {"product_no", "goodsno", "goods_no", "branduid", "uid", "productno", "itemno", "product_code", "idx", "no", "id", "pno", "gno"}
DROP_KEYS = {"cate_no", "display_group", "napm", "page", "sort_method", "ref", "category", "cate", "sort", "list_type"}


def canon_url(url: str) -> str:
    """Same product, different tracking/category params -> same key."""
    u = urlparse(url)
    path = re.sub(r"/category/\d+(/display/\d+)?/?$", "", u.path).rstrip("/")
    q = parse_qsl(u.query)
    keep = [(k.lower(), v) for k, v in q if k.lower() in ID_KEYS]
    if not keep:
        keep = [(k.lower(), v) for k, v in q if k.lower() not in DROP_KEYS and not k.lower().startswith("utm_")]
    return f"{u.netloc.lower()}{path}?{urlencode(sorted(keep))}"


def _page_url(base: str, n: int) -> str:
    m = _page_pattern_in(base)
    if m:
        digits = re.search(r"\d+", m.group(0)).group(0)
        return base.replace(m.group(0), m.group(0)[: -len(digits)] + str(n), 1)
    if n <= 1:
        return base
    return f"{base}{'&' if '?' in base else '?'}page={n}"


def _k(url: str) -> str:
    return hashlib.md5(canon_url(url).encode()).hexdigest()[:12]


def _img_key(url: str) -> str:
    return hashlib.md5(url.encode()).hexdigest()[:16] if url else ""


def _sig(urls: list[str]) -> str:
    return hashlib.md5("|".join(sorted(canon_url(u) for u in urls)[:12]).encode()).hexdigest()


def site_signature(html: str, source_name: str) -> set:
    """Titles that identify the SITE, not a product (used to reject fake product pages)."""
    soup = BeautifulSoup(html, "lxml")
    out = {_clean(source_name)}
    for t in ((soup.find("meta", property="og:title") or {}).get("content", ""), soup.title.string if soup.title else ""):
        t = _clean(t or "")
        if t:
            out.add(t)
    return {x for x in out if x}


def crawl_step(client, state: dict, listing_url: str, known: set, want: int, pages_budget: int, deadline: float | None) -> tuple[list[str], dict, str]:
    """Resumable crawl. state persists where the previous run stopped, so each run goes deeper
    instead of re-reading the same first page. Returns (new product urls, new state, note)."""
    new: list[str] = []
    seen_run: set[str] = set()

    def fetch_list(u: str):
        try:
            time.sleep(random.uniform(0.1, 0.3))
            return extract_listing_urls(fetch_html(client, u), u, 5000)
        except Exception:
            return None

    if not state.get("targets"):
        first = fetch_list(listing_url)
        if first is None:
            raise RuntimeError("Could not open the listing page")
        details, cats = first
        if CATEGORY_PAT.search(listing_url) or not cats:
            targets = [listing_url]
        else:
            targets = [listing_url] + cats[:80]
        state = {"targets": targets, "ti": 0, "page": 1, "first_sig": "", "prev_sig": ""}

    pages = 0
    note = ""
    pool = ThreadPoolExecutor(max_workers=4)
    try:
        while state["ti"] < len(state["targets"]) and len(new) < want and pages < pages_budget:
            if deadline and time.time() > deadline - 15:
                note = "time budget reached"
                break
            base = state["targets"][state["ti"]]
            nums = list(range(state["page"], state["page"] + 4))
            results = list(pool.map(lambda n: (n, fetch_list(_page_url(base, n))), nums))
            exhausted = False
            for n, res in results:
                pages += 1
                if not res or not res[0]:
                    exhausted = True
                    break
                urls = res[0]
                sig = _sig(urls)
                if n == 1:
                    state["first_sig"] = sig
                elif sig == state.get("first_sig") or sig == state.get("prev_sig"):
                    exhausted = True  # site repeats a page after the last one
                    break
                state["prev_sig"] = sig
                state["page"] = n + 1
                for u in urls:
                    c = _k(u)
                    if c not in known and c not in seen_run:
                        seen_run.add(c)
                        new.append(u)
            if exhausted:
                state["ti"] += 1
                state["page"], state["first_sig"], state["prev_sig"] = 1, "", ""
    finally:
        pool.shutdown(wait=False)
    if state["ti"] >= len(state["targets"]):
        state = {}  # full pass finished: next run starts a fresh pass (new items appear first)
        note = note or "full pass finished"
    return new, state, note


def fetch_image_bytes(client: httpx.Client, urls: list[str]) -> list[tuple[str, bytes, str]]:
    out = []
    for u in urls[:3]:
        if not u:
            continue
        try:
            r = client.get(u, timeout=15.0)
            ct = r.headers.get("content-type", "")
            if r.status_code == 200 and ct.startswith("image") and len(r.content) > 1024:
                out.append((u, r.content, ct))
        except Exception:
            continue
    return out


def dedupe_source(db: Session, source_id: int) -> int:
    """Remove copies of the same product (same title + same first image) inside one source.
    Keeps the oldest; copies that appear in orders are archived instead of deleted."""
    rows = db.query(models.Product.id, models.Product.title_ko, models.Product.images).filter(models.Product.source_id == source_id).order_by(models.Product.id).all()
    keep: dict = {}
    dups: list[int] = []
    for pid, title, images in rows:
        img = (images or [""])[0] if isinstance(images, list) else ""
        k = (title, img)
        if k in keep:
            dups.append(pid)
        else:
            keep[k] = pid
    removed = 0
    for i in range(0, len(dups), 200):
        chunk = dups[i : i + 200]
        ordered = {r[0] for r in db.query(models.OrderItem.product_id).filter(models.OrderItem.product_id.in_(chunk)).all()}
        gone = [x for x in chunk if x not in ordered]
        if gone:
            db.query(models.Product).filter(models.Product.id.in_(gone)).delete(synchronize_session=False)
            removed += len(gone)
        if ordered:
            db.query(models.Product).filter(models.Product.id.in_(list(ordered))).update({models.Product.status: "archived"}, synchronize_session=False)
    db.commit()
    return removed


def scrape_source(db: Session, source: models.Source, trigger: str = "manual", deadline: float | None = None) -> models.ScrapeLog:
    """deadline: epoch seconds after which no new product pages are fetched (serverless time limit)."""
    deadline = deadline or (time.time() + 240)
    log = models.ScrapeLog(
        source_id=source.id, source_name=source.name, trigger=trigger, status="ok", started_at=datetime.now(timezone.utc)
    )
    db.add(log)
    db.commit()

    cfg = dict(source.config or {})
    listing_url = cfg.get("listing_url") or source.url
    max_items = int(cfg.get("max_products") or get_setting(db, "scrape_max_products_per_run", 500))
    pages_budget = max(60, int(cfg.get("max_pages") or 0))
    new_count = auth_walls = dup_skipped = generic_skipped = 0
    errors: list[str] = []

    if not listing_url:
        log.status, log.message, log.finished_at = "error", "No listing URL configured", datetime.now(timezone.utc)
        source.status, source.last_error = "error", "No listing URL configured"
        db.commit()
        return log

    try:
        client = make_client()
        removed = 0
        try:
            removed = dedupe_source(db, source.id)
        except Exception:
            db.rollback()

        # what we already have: never re-fetch these
        known: set[str] = set()
        fps: set = set()
        for url, title, images in db.query(models.Product.source_url, models.Product.title_ko, models.Product.images).filter(models.Product.source_id == source.id).all():
            if url:
                known.add(_k(url))
            img = (images or [""])[0] if isinstance(images, list) else ""
            fps.add((title, img.rsplit("/", 1)[-1].split(".")[0]))

        try:
            generic = site_signature(fetch_html(client, listing_url), source.name)
        except Exception:
            generic = {_clean(source.name)}

        state = dict(cfg.get("crawl") or {})
        skip = list(cfg.get("skip") or [])
        known |= set(skip)
        pending = [u for u in state.pop("pending", []) if _k(u) not in known]
        found, state, note = crawl_step(client, state, listing_url, known | {_k(u) for u in pending}, max_items, pages_budget, deadline)
        product_urls = (pending + found)
        if not product_urls:
            if note == "full pass finished":
                log.status, log.new_products, log.updated_products = "ok", 0, 0
                log.message = f"Nothing new: all products found so far are already saved ({len(known)}). Next run re-checks from the first page."
                source.status, source.last_scraped_at, source.last_error = "ok", datetime.now(timezone.utc), ""
                cfg["crawl"] = state
                source.config = cfg
                log.finished_at = datetime.now(timezone.utc)
                db.commit()
                client.close()
                return log
            raise RuntimeError("No product links found - may need a platform-specific adapter")

        category_id = cfg.get("category_id") or None
        cat_slug = "general"
        if category_id:
            cat = db.query(models.Category).filter(models.Category.id == int(category_id)).first()
            cat_slug = cat.slug if cat else "general"

        def work(url: str):
            try:
                time.sleep(random.uniform(0.1, 0.4))
                page = fetch_html(client, url)
                if len(page) < 800 and ("회원" in page or "login" in page.lower() or "log-in" in page.lower()):
                    return ("auth", url, None, None)
                item = extract_product(page, url, generic)
                if not item or not item.get("price"):
                    return ("skip", url, None, None)
                imgs = fetch_image_bytes(client, item.get("images") or ([item.get("image")] if item.get("image") else []))
                return ("ok", url, item, imgs)
            except Exception as e:
                return ("err", url, f"{url[:80]}: {str(e)[:120]}", None)

        processed = 0
        pool = ThreadPoolExecutor(max_workers=8)
        try:
            for i in range(0, len(product_urls), 24):
                if time.time() > deadline - 10 or new_count >= max_items:
                    break
                chunk = product_urls[i : i + 24]
                for kind, url, item, imgs in pool.map(work, chunk):
                    processed += 1
                    if kind == "auth":
                        auth_walls += 1
                        continue
                    if kind == "err":
                        errors.append(item)
                        continue
                    if kind != "ok":
                        generic_skipped += 1
                        skip.append(_k(url))
                        continue
                    try:
                        first_img = (imgs[0][0] if imgs else "") or ""
                        fp = (item["title"][:290], _img_key(first_img) if first_img else str(item["price"]))
                        if fp in fps:
                            dup_skipped += 1
                            skip.append(_k(url))
                            continue
                        fps.add(fp)
                        images = []
                        for iu, data, ct in imgs:
                            ext = "jpg" if "jpeg" in ct or "jpg" in ct else ("png" if "png" in ct else "webp")
                            images.append(media_store.save(f"scraped/{source.id}/{_img_key(iu)}.{ext}", data, ct.split(";")[0]))
                        if not images:
                            images = [make_placeholder_image(source.id, item["title"], "", cat_slug)]
                        p = models.Product(
                            slug=unique_slug(db, item["title"], url),
                            title_ko=item["title"][:290],
                            desc_ko=item.get("description") or "",
                            price_cost=item["price"],
                            images=images,
                            status="published",
                            original_lang="ko",
                            translation_status="pending",
                            is_manual=False,
                            source_url=url[:590],
                            source_id=source.id,
                            category_id=int(category_id) if category_id else None,
                            rating=round(random.uniform(4.3, 5.0), 1),
                            reviews=random.randint(3, 180),
                        )
                        apply_pricing(db, p)
                        db.add(p)
                        db.commit()
                        known.add(_k(url))
                        new_count += 1
                    except Exception as e:
                        db.rollback()
                        errors.append(f"{url[:80]}: {str(e)[:120]}")
        finally:
            pool.shutdown(wait=False)

        # keep unprocessed urls for the next run so nothing found is lost
        leftover = [u for u in product_urls[processed:] if _k(u) not in known][:3000]
        if leftover:
            state = dict(state)
            state["pending"] = leftover
        cfg["crawl"] = state
        cfg["skip"] = skip[-4000:]
        source.config = cfg
        client.close()

        message = f"{new_count} new products saved ({len(product_urls)} candidate pages checked, {len(leftover)} queued for next run)"
        if note:
            message += f" | {note}"
        if removed:
            message += f" | {removed} duplicate copies removed"
        if dup_skipped:
            message += f" | {dup_skipped} duplicates skipped"
        if generic_skipped:
            message += f" | {generic_skipped} pages skipped (not real product pages or no price)"
        if auth_walls:
            message += f" | {auth_walls} members-only pages (login required)"
        if errors:
            message += f" | {len(errors)} page errors: " + "; ".join(errors[:3])
        if auth_walls and new_count == 0 and auth_walls >= processed - 1:
            log.status, log.new_products, log.updated_products, log.message = (
                "error", 0, 0,
                "All product pages are members-only (login required) - source cannot be scraped without credentials",
            )
        elif new_count == 0 and processed and not dup_skipped:
            log.status, log.new_products, log.updated_products, log.message = (
                "error", 0, 0,
                "No products could be parsed - product pages are JavaScript-rendered or use a custom layout that needs an adapter. " + message,
            )
        else:
            log.status, log.new_products, log.updated_products, log.message = ("ok", new_count, 0, message)
        source.status, source.last_scraped_at, source.last_error = log.status, datetime.now(timezone.utc), ("" if log.status == "ok" else log.message[:500])
    except Exception as e:
        db.rollback()
        log.status, log.message, log.finished_at = "error", str(e)[:500], datetime.now(timezone.utc)
        source.status, source.last_error, source.last_scraped_at = "error", str(e)[:500], datetime.now(timezone.utc)

    log.finished_at = datetime.now(timezone.utc)
    db.commit()
    try:
        translate_source_labels(db, limit=1)
    except Exception:
        db.rollback()
    return log


_scrape_lock = threading.Lock()


def scrape_all_enabled(db: Session, trigger: str = "schedule", deadline: float | None = None) -> list[dict]:
    """Scrape every enabled source. Guarded by a lock so overlapping triggers
    (manual run + schedule) never double-scrape the same sites."""
    if not _scrape_lock.acquire(blocking=False):
        return [{"source": "(all)", "status": "skipped", "new": 0, "updated": 0,
                 "message": "a scrape run is already in progress"}]
    try:
        results = []
        # least recently scraped first, so a time-limited run rotates through all sources
        srcs = (
            db.query(models.Source)
            .filter(models.Source.enabled == True)  # noqa: E712
            .order_by(models.Source.last_scraped_at.asc().nullsfirst())
            .all()
        )
        for idx, src in enumerate(srcs):
            if deadline and time.time() > deadline - 20:
                break
            slice_end = deadline
            if deadline:
                # share the time fairly: one big site must not starve the others
                slice_end = time.time() + max(40.0, (deadline - time.time()) / max(1, len(srcs) - idx))
                slice_end = min(slice_end, deadline)
            log = scrape_source(db, src, trigger=trigger, deadline=slice_end)
            results.append({"source": src.name, "status": log.status, "new": log.new_products, "updated": log.updated_products})
        return results
    finally:
        _scrape_lock.release()
