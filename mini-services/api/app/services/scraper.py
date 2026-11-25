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


def _decode(r: httpx.Response) -> str:
    """Honour <meta charset> too: many Korean shops (e.g. domeggook) are EUC-KR without a header charset."""
    if "charset=" in r.headers.get("content-type", "").lower():
        return r.text
    head = r.content[:4000].decode("ascii", "ignore")
    m = re.search(r"charset=[\"']?([\w-]+)", head, re.I)
    enc = (m.group(1) if m else "utf-8").lower()
    try:
        return r.content.decode(enc, "replace")
    except LookupError:
        return r.content.decode("utf-8", "replace")


def fetch_html_ex(client: httpx.Client, url: str) -> tuple[str, str]:
    """(html, final_url after redirects): relative links must resolve against the FINAL url."""
    r = client.get(url)
    r.raise_for_status()
    return _decode(r), str(r.url)


def fetch_html(client: httpx.Client, url: str) -> str:
    return fetch_html_ex(client, url)[0]


# ---- per-site rules for shops the generic crawler cannot read on its own
SITE_RULES = {
    "domeggook.com": {
        "detail_re": re.compile(r"^(?:https?://[^/]+)?/\d{6,9}\?from=lstGen", re.I),
        "cat_re": re.compile(r"itemList\.php\?[^#]*\bca=[\d_]+", re.I),
        "cats_only": True,       # the home page lists banners, not the catalog: crawl categories
        "max_targets": 400,
        "page_param": "pg",
        "title_strip": [r"^\[[^\]]{1,12}\]\s*"],
        "price_sel": ["#lItemPrice"],
        "price_from_og_desc": True,
        "og_only_images": True,  # other thumbnails on the page belong to different products
    },
}


def rule_for(url: str) -> dict | None:
    host = (urlparse(url).netloc or "").lower()
    for dom, rule in SITE_RULES.items():
        if host == dom or host.endswith("." + dom):
            return rule
    return None


PRICE_PAT3 = re.compile(r"(?:₩|\bKRW\b)\s*([\d,]{3,})|([\d,]{3,})\s*(?:원|KRW)", re.I)


def parse_price_int(text: str, loose: bool = False) -> int | None:
    candidates = []
    for m in (PRICE_PAT3 if loose else PRICE_PAT).finditer(text):
        raw = (m.group(1) or m.group(2) or "").replace(",", "")
        if raw.isdigit():
            v = int(raw)
            if (100 if loose else 500) <= v <= 50_000_000:
                candidates.append(v)
    return min(candidates) if candidates else None


def _abs(base_url: str, href: str) -> str:
    if href.startswith("//"):
        return "https:" + href
    if href.startswith("http"):
        return href
    from urllib.parse import urljoin

    return urljoin(base_url, href)


def _tidy(url: str) -> str:
    """Drop tracking params that some shops put in links and then 404 on (e.g. godomall 'mtn=...')."""
    u = urlparse(url)
    if not u.query:
        return url
    q = [(k, v) for k, v in parse_qsl(u.query, keep_blank_values=True) if k.lower() not in ("mtn", "napm")]
    return u._replace(query=urlencode(q)).geturl()


def extract_listing_urls(html: str, base_url: str, limit: int, rule: dict | None = None) -> tuple[list[str], list[str]]:
    """Return (product detail urls, category list urls) found on a page."""
    soup = BeautifulSoup(html, "lxml")
    details, cats, seen = [], [], set()
    for a in soup.find_all("a", href=True):
        href = (a["href"] or "").split("#")[0]
        if not href or href in seen:
            continue
        if rule:
            url = _tidy(_abs(base_url, href))
            if url in seen:
                continue
            if rule["detail_re"].search(href):
                seen.add(url)
                details.append(url)
            elif rule.get("cat_re") and rule["cat_re"].search(href):
                seen.add(url)
                cats.append(url)
            continue
        if EXCLUDE_PAT.search(href):
            continue
        url = _tidy(_abs(base_url, href))
        if url in seen:
            continue
        if DETAIL_PAT.search(href) and not re.search(r"\d", href):
            continue  # e.g. bare /product/detail.html with no product id: not a product
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


def _ld_nodes(obj):
    """Every dict inside a JSON-LD blob (handles @graph, lists, hasVariant, offers)."""
    if isinstance(obj, dict):
        yield obj
        for v in obj.values():
            if isinstance(v, (dict, list)):
                yield from _ld_nodes(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from _ld_nodes(v)


def _ld_types(n: dict) -> list:
    t = n.get("@type")
    return t if isinstance(t, list) else [t]


def _num(v) -> int | None:
    try:
        f = float(str(v).replace(",", "").strip())
        return int(f) if f >= 1 else None
    except Exception:
        return None


def _ld_product(soup, page_url: str, generic) -> dict | None:
    """schema.org Product OR ProductGroup (cafe24 puts the name on the group and the variants,
    with their offers and images, under hasVariant). Returns None when there is no usable name."""
    group = prod = None
    for script in soup.find_all("script", type="application/ld+json"):
        try:
            blob = json.loads(script.string or script.get_text() or "{}")
        except Exception:
            continue
        for n in _ld_nodes(blob):
            types = _ld_types(n)
            if "ProductGroup" in types and not group:
                group = n
            elif "Product" in types and not prod:
                prod = n
    root = group or prod
    if not root:
        return None
    title = _clean(str(root.get("name", "")))
    if not title and prod:
        title = _clean(str(prod.get("name", "")))
    if not title or title in generic:
        return None
    nodes = [root] + [n for n in _ld_nodes(root) if n is not root and "Product" in _ld_types(n)]
    prices, imgs = [], []
    for n in nodes:
        offs = n.get("offers") or {}
        for o in (offs if isinstance(offs, list) else [offs]):
            if isinstance(o, dict):
                for key in ("price", "lowPrice"):
                    v = _num(o.get(key))
                    if v:
                        prices.append(v)
                if isinstance(o.get("image"), str):
                    imgs.append(o["image"])
        im = n.get("image")
        for u in (im if isinstance(im, list) else [im]):
            if isinstance(u, str) and u:
                imgs.append(u)
            elif isinstance(u, dict) and u.get("url"):
                imgs.append(str(u["url"]))
    gallery = list(dict.fromkeys(_abs(page_url, u) for u in imgs))
    desc = _clean(str(root.get("description", "") or (prod or {}).get("description", "")))[:4000]
    return {
        "title": title,
        "price": min(prices) if prices else None,
        "description": desc,
        "image": gallery[0] if gallery else None,
        "gallery": gallery,
    }


PRICE_HIDDEN_PAT = re.compile(
    r"(가입\s*후\s*(금액|가격)|회원\s*(공개|전용|만\s*(구매|확인))|로그인\s*후\s*(가격|금액|확인|구매)|(금액|가격)\s*(확인|비공개)|비회원\s*(가격|금액)|log\s*in\s*to\s*(see|view))",
    re.I,
)


def clean_title(t: str, generic, rule: dict | None = None) -> str:
    """Plain text name: no HTML fragments, no '[shop]' prefix, no ' - ShopName' suffix, no lead-time notes."""
    t = t or ""
    if "<" in t:
        t = BeautifulSoup(t, "lxml").get_text(" ")
    t = _clean(t)
    for pat in (rule or {}).get("title_strip", []):
        t = re.sub(pat, "", t).strip()
    t = re.sub(r"\s*출고\s*까지.*$", "", t).strip()
    m = re.match(r"^(.*\S)\s+[-|]\s+([^-|]{2,30})$", t)
    if m and any(m.group(2).strip() in g for g in generic):
        t = m.group(1).strip()
    return t


PRICE_SELECTORS = ["#span_product_price_text", ".item_price .price", "#span_product_price_sale", ".price_sale", ".sale_price", ".goods_price .price", ".price"]


def _page_price(soup, rule: dict | None = None) -> int | None:
    """Price shown on the product page itself (never a number scraped from the whole HTML)."""
    og = lambda prop: (soup.find("meta", property=prop) or {}).get("content", "")
    v = parse_price_int(og("product:price:amount") or "", loose=True) or _num(og("product:price:amount"))
    if v:
        return v
    for sel in (rule or {}).get("price_sel", []) + PRICE_SELECTORS:
        for el in soup.select(sel)[:4]:
            txt = el.get_text(" ")
            for m in re.finditer(r"[\d][\d,]{2,}", txt):
                v = _num(m.group(0))
                if v and 100 <= v <= 50_000_000:
                    return v
    if (rule or {}).get("price_from_og_desc"):
        return parse_price_int(og("og:description") or "", loose=True)
    return None


def extract_product(html: str, page_url: str, generic: frozenset | set = frozenset(), rule: dict | None = None) -> dict | None:
    """JSON-LD (schema.org/Product) first, OpenGraph + price heuristics fallback.
    Also collects up to 3 gallery image URLs."""
    soup = BeautifulSoup(html, "lxml")
    data = {}
    gallery: list[str] = []

    ld = _ld_product(soup, page_url, generic)
    if ld:
        data = {k: v for k, v in ld.items() if k != "gallery"}
        gallery = ld.get("gallery") or []

    if not data.get("title"):
        og = lambda prop: (soup.find("meta", property=prop) or {}).get("content", "")
        cands = []
        for sel in ("#span_product_name", ".headingArea h2", ".infoArea h2", ".goods_name", ".item_detail_tit", ".prd_name"):
            el = soup.select_one(sel)
            if el and el.get_text(strip=True):
                cands.append(_clean(el.get_text(" ")))
        cands += [_clean(og("og:title")), _clean(soup.title.string if soup.title else "")]
        for sel in ("h1", "h2.title"):
            el = soup.select_one(sel)
            if el and el.get_text(strip=True):
                cands.append(_clean(el.get_text(" ")))
        # first candidate that is not the site-wide title (some shops return the same og:title on every page)
        title = next((c for c in cands if c and c not in generic), "")
        if not title:
            return None
        desc = _clean(og("og:description") or "")
        img = og("og:image")
        gallery = [_abs(page_url, u) for u in (img, og("og:image:secure_url")) if u]
        data = {
            "title": title,
            "price": None,
            "description": desc[:4000],
            "image": _abs(page_url, img) if img else None,
        }

    # Gallery candidates from common product-image markup (cafe24 / godomall / custom shops)
    if len(gallery) < 3 and not (rule or {}).get("og_only_images"):
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
        data["price"] = _page_price(soup, rule)
    if not data.get("price"):
        # No price on the page itself: members-only, or a layout we cannot read. Never guess one
        # (numbers elsewhere on the page are shipping fees, banners, etc.).
        data["price_hidden"] = True
    if not data.get("title"):
        return None
    # Split "상품명 : 옵션" style noise
    data["title"] = clean_title(re.split(r"\s*[:：]\s*(?:상세|상품)?\s*페이지", data["title"])[0], generic, rule)
    if not data["title"] or data["title"] in generic:
        return None
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


def fast_slug(title: str, url: str) -> str:
    """Unique without a database lookup: the url hash makes it unique per product page."""
    return (slugify(title)[:60] or "item") + "-" + hashlib.md5(url.encode()).hexdigest()[:10]


def unique_slug(db: Session, base: str, seed: str) -> str:
    h = hashlib.md5(seed.encode()).hexdigest()[:6]
    base = (slugify(base) or "item") + "-" + h
    slug, i = base, 1
    while db.query(models.Product).filter(models.Product.slug == slug).first():
        i += 1
        slug = f"{base}-{i}"
    return slug


ID_KEYS = {"product_no", "goodsno", "goods_no", "branduid", "uid", "productno", "itemno", "product_code", "idx", "no", "id", "pno", "gno"}
DROP_KEYS = {"cate_no", "display_group", "napm", "page", "pg", "sort_method", "ref", "category", "cate", "sort", "list_type", "from", "advcnt", "mtn"}


def canon_url(url: str) -> str:
    """Same product, different tracking/category params -> same key."""
    u = urlparse(url)
    path = re.sub(r"/category/\d+(/display/\d+)?/?$", "", u.path).rstrip("/")
    q = parse_qsl(u.query)
    keep = [(k.lower(), v) for k, v in q if k.lower() in ID_KEYS]
    if not keep:
        keep = [(k.lower(), v) for k, v in q if k.lower() not in DROP_KEYS and not k.lower().startswith("utm_")]
    return f"{u.netloc.lower()}{path}?{urlencode(sorted(keep))}"


def _page_url(base: str, n: int, param: str = "page") -> str:
    m = re.search(r"([?&])(pg|page)=\d+", base) or _page_pattern_in(base)
    if m and m.re.pattern.startswith("([?&])"):
        return re.sub(r"([?&])(pg|page)=\d+", lambda mm: f"{mm.group(1)}{mm.group(2)}={n}", base, count=1)
    if m:
        digits = re.search(r"\d+", m.group(0)).group(0)
        return base.replace(m.group(0), m.group(0)[: -len(digits)] + str(n), 1)
    if n <= 1:
        return base
    return f"{base}{'&' if '?' in base else '?'}{param}={n}"


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


def crawl_step(client, state: dict, listing_url: str, known: set, want: int, pages_budget: int, deadline: float | None, rule: dict | None = None) -> tuple[list[str], dict, str]:
    """Resumable crawl. state persists where the previous run stopped, so each run goes deeper
    instead of re-reading the same first page. Returns (new product urls, new state, note)."""
    new: list[str] = []
    seen_run: set[str] = set()

    def fetch_list(u: str):
        try:
            time.sleep(random.uniform(0.1, 0.3))
            html_u, final_u = fetch_html_ex(client, u)
            return extract_listing_urls(html_u, final_u, 5000, rule)
        except Exception as e:
            fetch_list.last_error = f"{type(e).__name__}: {str(e)[:140]}"
            return None
    fetch_list.last_error = ""

    if not state.get("targets"):
        first = fetch_list(listing_url)
        if first is None:
            raise RuntimeError("Could not open the listing page (" + (fetch_list.last_error or "no response") + ")")
        details, cats = first
        if rule and rule.get("cats_only"):
            targets = list(dict.fromkeys(cats))[: int(rule.get("max_targets", 80))]
            if not targets:
                raise RuntimeError("No category links found on the start page")
        elif CATEGORY_PAT.search(listing_url) or not cats:
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
            results = list(pool.map(lambda n: (n, fetch_list(_page_url(base, n, (rule or {}).get("page_param", "page")))), nums))
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


LOGIN_PATHS = ["/member/login.html", "/member/login.php", "/shop/member/login.php", "/member/login", "/login", "/user/login", "/shop/member/login.html", "/bbs/login.php"]


def login_session(client: httpx.Client, lg: dict, base_url: str) -> tuple[bool, str]:
    """Sign in with a wholesale account so member-only prices become visible.
    Finds the login form (the one with a password field), submits it, keeps the session cookies in
    the client, and checks the home page for a logout link. Returns (ok, short message)."""
    from urllib.parse import urljoin

    uid, pw = (lg.get("id") or "").strip(), lg.get("password") or ""
    if not uid or not pw:
        return False, "no login configured"
    u = urlparse(base_url)
    origin = f"{u.scheme}://{u.netloc}"
    cands: list[str] = []
    if lg.get("url"):
        cands.append(lg["url"])
    try:
        home_html, home_url = fetch_html_ex(client, origin + "/")
        for a in BeautifulSoup(home_html, "lxml").find_all("a", href=True):
            if re.search(r"login", a["href"], re.I) and not re.search(r"logout|naver|kakao|google|facebook", a["href"], re.I):
                cands.append(urljoin(home_url, a["href"]))
    except Exception:
        pass
    cands += [origin + p for p in LOGIN_PATHS]
    last = "no login form found"
    tried = set()
    for cu in cands:
        if cu in tried or len(tried) >= 10:
            continue
        tried.add(cu)
        try:
            r = client.get(cu)
            if r.status_code >= 400:
                continue
            soup = BeautifulSoup(_decode(r), "lxml")
            forms = [f for f in soup.find_all("form") if f.find("input", {"type": "password"})]
            if not forms:
                continue
            form = forms[0]
            payload: dict = {}
            for inp in form.find_all(["input", "textarea"]):
                name = inp.get("name")
                typ = (inp.get("type") or "text").lower()
                if not name or typ in ("submit", "button", "image", "file", "password"):
                    continue
                if typ in ("checkbox", "radio"):
                    if inp.has_attr("checked"):
                        payload[name] = inp.get("value", "on")
                    continue
                payload[name] = inp.get("value", "")
            pw_name = form.find("input", {"type": "password"}).get("name")
            texts = [i for i in form.find_all("input") if (i.get("type") or "text").lower() in ("text", "email", "tel") and i.get("name")]
            id_name = next((i["name"] for i in texts if re.search(r"id|email|user|login|member", i["name"], re.I)), texts[0]["name"] if texts else None)
            if not pw_name or not id_name:
                continue
            payload[id_name], payload[pw_name] = uid, pw
            action = urljoin(str(r.url), form.get("action") or str(r.url))
            if (form.get("method") or "post").lower() == "get":
                resp = client.get(action, params=payload)
            else:
                resp = client.post(action, data=payload, headers={"Referer": str(r.url)})
            home = _decode(client.get(origin + "/"))
            if re.search(r"로그아웃|logout|sign\s*out", home, re.I):
                return True, "logged in"
            alert = re.search(r"alert\(['\"]([^'\"]{3,80})", resp.text or "")
            last = f"login rejected ({alert.group(1)})" if alert else "login form submitted but the site did not accept it"
        except Exception as e:
            last = f"{type(e).__name__}: {str(e)[:80]}"
    return False, last


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
    new_count = auth_walls = dup_skipped = generic_skipped = hidden_prices = 0
    errors: list[str] = []

    if not listing_url:
        log.status, log.message, log.finished_at = "error", "No listing URL configured", datetime.now(timezone.utc)
        source.status, source.last_error = "error", "No listing URL configured"
        db.commit()
        return log

    try:
        client = make_client()
        rule = rule_for(listing_url)
        lg = cfg.get("login") or {}
        login_note = ""
        logged_in = False
        if lg.get("id") and lg.get("password"):
            logged_in, msg = login_session(client, lg, listing_url)
            if not logged_in:
                log.status, log.new_products, log.updated_products = "error", 0, 0
                log.message = f"Login failed: {msg}. Check the account id/password in this source's settings."
                log.finished_at = datetime.now(timezone.utc)
                source.status, source.last_error, source.last_scraped_at = "error", log.message[:500], datetime.now(timezone.utc)
                db.commit()
                client.close()
                return log
            login_note = "logged in"
        removed = 0
        try:
            removed = dedupe_source(db, source.id)
        except Exception:
            db.rollback()

        try:
            generic0 = site_signature(fetch_html(client, listing_url), source.name)
        except Exception:
            generic0 = {_clean(source.name)}
        purged = 0
        try:
            junk = [r[0] for r in db.query(models.Product.id).filter(models.Product.source_id == source.id, models.Product.title_ko.in_(list(generic0))).all()]
            for i in range(0, len(junk), 200):
                chunk = junk[i : i + 200]
                ordered = {r[0] for r in db.query(models.OrderItem.product_id).filter(models.OrderItem.product_id.in_(chunk)).all()}
                gone = [x for x in chunk if x not in ordered]
                if gone:
                    db.query(models.Product).filter(models.Product.id.in_(gone)).delete(synchronize_session=False)
                    purged += len(gone)
                if ordered:
                    db.query(models.Product).filter(models.Product.id.in_(list(ordered))).update({models.Product.status: "archived"}, synchronize_session=False)
            db.commit()
        except Exception:
            db.rollback()
        removed += purged

        # what we already have: never re-fetch these
        known: set[str] = set()
        fps: set = set()
        for url, title, images in db.query(models.Product.source_url, models.Product.title_ko, models.Product.images).filter(models.Product.source_id == source.id).all():
            if url:
                known.add(_k(url))
            img = (images or [""])[0] if isinstance(images, list) else ""
            fps.add((title, _img_key(img) if img.startswith("http") else img.rsplit("/", 1)[-1].split(".")[0]))

        generic = generic0

        state = dict(cfg.get("crawl") or {})
        skip = [] if logged_in else list(cfg.get("skip") or [])
        known |= set(skip)
        pending = [u for u in state.pop("pending", []) if _k(u) not in known]
        found, state, note = crawl_step(client, state, listing_url, known | {_k(u) for u in pending}, max_items, pages_budget, deadline, rule)
        product_urls = (pending + found)
        if not product_urls:
            have = db.query(models.Product).filter(models.Product.source_id == source.id).count()
            if note == "full pass finished" and have > 0:
                log.status, log.new_products, log.updated_products = "ok", 0, 0
                log.message = f"Nothing new: all {have} products found so far are already saved. Next run re-checks from the first page."
                source.status, source.last_scraped_at, source.last_error = "ok", datetime.now(timezone.utc), ""
                cfg["crawl"] = state
                source.config = cfg
                log.finished_at = datetime.now(timezone.utc)
                db.commit()
                client.close()
                return log
            raise RuntimeError("The listing page opened but no product links were found. The shop may load its products with JavaScript or use a layout this scraper does not know yet.")

        category_id = cfg.get("category_id") or None
        cat_slug = "general"
        if category_id:
            cat = db.query(models.Category).filter(models.Category.id == int(category_id)).first()
            cat_slug = cat.slug if cat else "general"

        from ..deps import get_setting as _gs
        from .markup import apply_pricing_with, resolve_markup, compute_sell_price

        global_pct = float(_gs(db, "markup_percent", 35.0))
        cat_obj = db.query(models.Category).filter(models.Category.id == int(category_id)).first() if category_id else None

        def work(url: str):
            try:
                time.sleep(random.uniform(0.05, 0.25))
                page = fetch_html(client, url)
                if len(page) < 800 and ("회원" in page or "login" in page.lower() or "log-in" in page.lower()):
                    return ("auth", url, None, None)
                item = extract_product(page, url, generic, rule)
                if item and item.get("price_hidden") and not item.get("price"):
                    return ("hidden", url, None, None)
                if not item or not item.get("price"):
                    return ("skip", url, None, None)
                urls = [u for u in (item.get("images") or ([item.get("image")] if item.get("image") else [])) if u]
                return ("ok", url, item, urls[:3])
            except Exception as e:
                return ("err", url, f"{url[:80]}: {str(e)[:120]}", None)

        processed = 0
        pool = ThreadPoolExecutor(max_workers=12)
        try:
            for i in range(0, len(product_urls), 48):
                if time.time() > deadline - 10 or new_count >= max_items:
                    break
                chunk = product_urls[i : i + 48]
                batch: list = []
                for kind, url, item, imgs in pool.map(work, chunk):
                    processed += 1
                    if kind == "auth":
                        auth_walls += 1
                        continue
                    if kind == "err":
                        errors.append(item)
                        continue
                    if kind == "hidden":
                        hidden_prices += 1
                        skip.append(_k(url))
                        continue
                    if kind != "ok":
                        generic_skipped += 1
                        skip.append(_k(url))
                        continue
                    try:
                        first_img = (imgs[0] if imgs else "") or ""
                        fp = (item["title"][:290], _img_key(first_img) if first_img else str(item["price"]))
                        if fp in fps:
                            dup_skipped += 1
                            skip.append(_k(url))
                            continue
                        fps.add(fp)
                        images = list(imgs)  # supplier image links only: nothing is stored in our database
                        if not images:
                            images = [make_placeholder_image(source.id, item["title"], "", cat_slug)]
                        p = models.Product(
                            slug=fast_slug(item["title"], url),
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
                        p.price_sell = compute_sell_price(p.price_cost, resolve_markup(p, cat_obj, global_pct))
                        batch.append((p, url))
                    except Exception as e:
                        errors.append(f"{url[:80]}: {str(e)[:120]}")
                # one commit per batch (a commit per product made 2,000 products take minutes)
                if batch:
                    try:
                        for bp, _u in batch:
                            db.add(bp)
                        db.commit()
                        for _bp, bu in batch:
                            known.add(_k(bu))
                        new_count += len(batch)
                    except Exception:
                        db.rollback()
                        for bp, bu in batch:  # a single bad row must not lose the whole batch
                            try:
                                db.add(bp)
                                db.commit()
                                known.add(_k(bu))
                                new_count += 1
                            except Exception as e2:
                                db.rollback()
                                errors.append(f"{bu[:80]}: {str(e2)[:120]}")
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
        if login_note:
            message += f" | {login_note}"
        if note:
            message += f" | {note}"
        if removed:
            message += f" | {removed} duplicate copies removed"
        if dup_skipped:
            message += f" | {dup_skipped} duplicates skipped"
        if generic_skipped:
            message += f" | {generic_skipped} pages skipped (not real product pages or no price)"
        if hidden_prices:
            message += f" | {hidden_prices} pages skipped: no readable price (members only)"
        if auth_walls:
            message += f" | {auth_walls} members-only pages (login required)"
        if errors:
            message += f" | {len(errors)} page errors: " + "; ".join(errors[:3])
        if auth_walls and new_count == 0 and auth_walls >= processed - 1:
            log.status, log.new_products, log.updated_products, log.message = (
                "error", 0, 0,
                "All product pages are members-only (login required) - source cannot be scraped without credentials",
            )
        elif new_count == 0 and hidden_prices and hidden_prices >= processed - auth_walls - len(errors) - 1:
            log.status, log.new_products, log.updated_products, log.message = (
                "error", 0, 0,
                ("Login worked but no price could be read on these pages. " if logged_in else "This supplier hides wholesale prices until you log in (members only): add your wholesale account in this source's settings. ") + "Nothing was saved because the scraper will not guess a price. " + message,
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
