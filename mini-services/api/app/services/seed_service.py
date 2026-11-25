"""Seeding: settings, admin user, categories, supplier sources (from the uploaded Excel),
demo catalog with generated SVG images. Idempotent - safe to run on every boot."""
import hashlib
import json

from sqlalchemy.orm import Session

from .. import models
from ..config import DEFAULT_SETTINGS, SEED_ADMIN_EMAIL, SEED_ADMIN_PASSWORD, SEED_DIR
from ..security import hash_password
from . import media_store
from .markup import apply_pricing
from seed import demo_data

SEED_DIR.mkdir(exist_ok=True)


def seed_settings(db: Session):
    for key, value in DEFAULT_SETTINGS.items():
        if not db.query(models.Setting).filter(models.Setting.key == key).first():
            db.add(models.Setting(key=key, value=value))
    db.commit()
    # Upgrade default translation provider for stores that never configured one
    # One-time only: afterwards an admin choosing "none" must stick across restarts.
    if not db.query(models.Setting).filter(models.Setting.key == "_translate_default_upgraded").first():
        row = db.query(models.Setting).filter(models.Setting.key == "translate_provider").first()
        if row and row.value == "none":
            row.value = "google_free"
        db.add(models.Setting(key="_translate_default_upgraded", value=True))
        db.commit()


def _raise_scrape_limit(db: Session):
    """One-time: the old default of 10 products per run is far too low for full-catalog scraping."""
    if db.query(models.Setting).filter(models.Setting.key == "_scrape_limit_raised").first():
        return
    row = db.query(models.Setting).filter(models.Setting.key == "scrape_max_products_per_run").first()
    if row and int(row.value or 0) < 100:
        row.value = 500
    db.add(models.Setting(key="_scrape_limit_raised", value=True))
    db.commit()


def seed_admin(db: Session):
    """Create the admin once. Emails are stored lower-case (login lower-cases what you type).

    Forgot / never applied the env password? Set SHOPEE_ADMIN_RESET=1 (plus SHOPEE_ADMIN_EMAIL and
    SHOPEE_ADMIN_PASSWORD), redeploy once, log in, then remove SHOPEE_ADMIN_RESET.
    """
    import os

    from ..security import verify_password

    email = SEED_ADMIN_EMAIL.strip().lower()
    user = db.query(models.User).filter(models.User.email == email).first()
    if not user:
        db.add(models.User(email=email, password_hash=hash_password(SEED_ADMIN_PASSWORD), role="admin"))
        db.commit()
    elif os.getenv("SHOPEE_ADMIN_RESET") == "1" and not verify_password(SEED_ADMIN_PASSWORD, user.password_hash):
        user.password_hash = hash_password(SEED_ADMIN_PASSWORD)
        user.role = "admin"
        db.commit()
    # repair rows created before emails were lower-cased
    for u in db.query(models.User).all():
        if u.email != u.email.strip().lower():
            u.email = u.email.strip().lower()
    db.commit()


def seed_categories(db: Session):
    for i, c in enumerate(demo_data.CATEGORIES):
        if not db.query(models.Category).filter(models.Category.slug == c["slug"]).first():
            db.add(models.Category(slug=c["slug"], name_en=c["name_en"], name_ko=c["name_ko"], sort_order=i))
    db.commit()


def map_hint_to_category(hint: str) -> str:
    for pat, slug in demo_data.HINT_MAP:
        if pat in (hint or ""):
            return slug
    return "general"


def seed_sources(db: Session):
    path = SEED_DIR / "sources.json"
    if not path.exists():
        return 0
    data = json.loads(path.read_text(encoding="utf-8"))
    cat_by_slug = {c.slug: c.id for c in db.query(models.Category).all()}
    added = 0
    for row in data:
        if db.query(models.Source).filter(models.Source.name == row["name"]).first():
            continue
        slug = map_hint_to_category(row["category_hint"])
        db.add(
            models.Source(
                name=row["name"],
                url=row["url"],
                category_hint=row["category_hint"],
                products_hint=row["products_hint"],
                contact=row["contact"],
                notes=row["notes"],
                image_provided=bool(row["image_provided"]),
                dropship_possible=bool(row["dropship_possible"]),
                paid_membership=bool(row["paid_membership"]),
                requires_cafe=bool(row["requires_cafe"]),
                adapter="generic",
                config={"category_id": cat_by_slug.get(slug)},
                enabled=False,
                status="new",
            )
        )
        added += 1
    db.commit()
    return added


def _svg_placeholder(slug: str, title_ko: str, title_en: str, code: str, cat_slug: str) -> str:
    c1, c2 = demo_data.GRADIENTS.get(cat_slug, ("#FDBA74", "#EA580C"))
    lines = []
    words = (title_en or title_ko).split(" ")
    cur = ""
    for w in words:
        if len(cur) + len(w) > 24:
            lines.append(cur)
            cur = w
        else:
            cur = (cur + " " + w).strip()
        if len(lines) == 2:
            break
    if cur and len(lines) < 2:
        lines.append(cur)
    line1 = lines[0] if lines else title_en
    line2 = lines[1] if len(lines) > 1 else ""
    big = (title_ko[:26]) if len(title_ko) <= 26 else title_ko[:25] + "…"
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="800" height="800" viewBox="0 0 800 800">
  <defs>
    <linearGradient id="g" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0" stop-color="{c1}"/><stop offset="1" stop-color="{c2}"/>
    </linearGradient>
  </defs>
  <rect width="800" height="800" fill="url(#g)"/>
  <circle cx="660" cy="140" r="110" fill="#ffffff" opacity="0.12"/>
  <circle cx="120" cy="640" r="150" fill="#ffffff" opacity="0.10"/>
  <circle cx="700" cy="700" r="70" fill="#ffffff" opacity="0.14"/>
  <rect x="0" y="0" width="800" height="12" fill="#ffffff" opacity="0.35"/>
  <text x="60" y="120" font-family="Inter, sans-serif" font-size="30" font-weight="700" fill="#ffffff" opacity="0.9">{cat_slug.upper()}</text>
  <text x="400" y="400" text-anchor="middle" font-family="'Noto Sans KR', Inter, sans-serif" font-size="52" font-weight="800" fill="#ffffff">{big}</text>
  <text x="400" y="465" text-anchor="middle" font-family="Inter, sans-serif" font-size="34" font-weight="600" fill="#ffffff" opacity="0.92">{line1}</text>
  <text x="400" y="512" text-anchor="middle" font-family="Inter, sans-serif" font-size="34" font-weight="600" fill="#ffffff" opacity="0.92">{line2}</text>
  <text x="60" y="742" font-family="Inter, sans-serif" font-size="26" font-weight="700" fill="#ffffff" opacity="0.85">{code}</text>
</svg>'''


def seed_demo_products(db: Session):
    if db.query(models.Product).count() > 0:
        return 0
    cat_by_slug = {c.slug: c for c in db.query(models.Category).all()}
    added = 0
    for item in demo_data.PRODUCTS:
        cat = cat_by_slug.get(item["cat"])
        slug = f'{item["cat"]}-{item["code"].lower()}-{hashlib.md5(item["title_ko"].encode()).hexdigest()[:6]}'
        img_url = media_store.save(
            f"seed/{slug}.svg",
            _svg_placeholder(slug, item["title_ko"], item["title_en"], item["code"], item["cat"]).encode("utf-8"),
            "image/svg+xml",
        )
        p = models.Product(
            slug=slug,
            title_ko=item["title_ko"],
            title_en=item["title_en"],
            desc_ko=item["desc_ko"],
            desc_en=item["desc_en"],
            price_cost=item["cost"],
            images=[img_url],
            status="published",
            original_lang="ko",
            translation_status="done",
            is_manual=True,
            rating=item["rating"],
            reviews=item["reviews"],
            category_id=cat.id if cat else None,
            stock_status="in_stock",
        )
        apply_pricing(db, p)
        db.add(p)
        added += 1
    db.commit()
    return added


# Sources verified reachable + scrapable (probe run against the live sites).
# Each gets a listing config so the generic scraper can pull products.
VERIFIED_SOURCES = [
    "리얼백", "소품마켓", "커먼샵(가방장인)", "크레이지리스트", "펫모닝", "펫토리", "도매꾹", "오너클랜",
    "온채널", "도매콜", "도매로", "젠트레이드", "신상마켓", "펀타스틱",
]

# The supplier list the store works with: matched by website, so duplicates and renamed rows are handled.
KEEP_DOMAINS = [
    "realbag.kr", "asopoom.com", "comeonshop.co.kr", "crazylist.co.kr", "petmorning45.cafe24.com", "pettory.com",
    "domeggook.com", "ownerclan.com", "onch3.co.kr", "domecall.net", "domero.net", "domebookmark.com",
    "zentrade.co.kr", "sinsangmarket.kr", "funtasticb2b.co.kr",
]
PREFERRED_NAMES = {"젠트레이드", "펀타스틱", "오너클랜", "소품마켓"}
DISABLED_DOMAINS = {"domebookmark.com"}  # the domain now serves an unrelated site: kept in the list but never scraped
LISTING_OVERRIDES = {"realbag.kr": "https://www.realbag.kr/product/list.html?cate_no=150"}


def _domain_of(url: str) -> str:
    from urllib.parse import urlparse

    host = (urlparse(url or "").netloc or "").lower()
    for d in KEEP_DOMAINS:
        if host == d or host.endswith("." + d):
            return d
    return ""


def trim_sources(db: Session) -> dict:
    """One-time: keep only the chosen suppliers. Everything else is removed together with its products
    (products that appear in orders are archived instead, so order history stays intact)."""
    if db.query(models.Setting).filter(models.Setting.key == "_sources_trimmed_v1").first():
        return {"skipped": True}
    sources = db.query(models.Source).order_by(models.Source.id).all()
    keep: dict[str, models.Source] = {}
    for src in sources:
        d = _domain_of(src.url) or _domain_of((src.config or {}).get("listing_url", ""))
        if not d:
            continue
        cur = keep.get(d)
        if cur is None or (src.name in PREFERRED_NAMES and cur.name not in PREFERRED_NAMES):
            keep[d] = src
    keep_ids = {x.id for x in keep.values()}
    removed_sources = removed_products = 0
    for src in sources:
        if src.id in keep_ids:
            continue
        pids = [r[0] for r in db.query(models.Product.id).filter(models.Product.source_id == src.id).all()]
        for i in range(0, len(pids), 200):
            chunk = pids[i : i + 200]
            ordered = {r[0] for r in db.query(models.OrderItem.product_id).filter(models.OrderItem.product_id.in_(chunk)).all()}
            gone = [x for x in chunk if x not in ordered]
            if gone:
                db.query(models.Product).filter(models.Product.id.in_(gone)).delete(synchronize_session=False)
                removed_products += len(gone)
            if ordered:
                db.query(models.Product).filter(models.Product.id.in_(list(ordered))).update(
                    {models.Product.source_id: None, models.Product.status: "archived"}, synchronize_session=False
                )
        db.delete(src)
        removed_sources += 1
    for d, src in keep.items():
        cfg = dict(src.config or {})
        cfg.pop("crawl", None)
        cfg.pop("skip", None)
        cfg["listing_url"] = LISTING_OVERRIDES.get(d) or cfg.get("listing_url") or src.url
        cfg["max_products"] = max(int(cfg.get("max_products") or 0), 2000)
        src.config = cfg
        src.adapter = "generic"
        src.status, src.last_error = "new", ""
        src.enabled = d not in DISABLED_DOMAINS
        if d in DISABLED_DOMAINS:
            src.notes = ((src.notes or "") + " | Domain now serves an unrelated site: disabled.").strip(" |")
    db.add(models.Setting(key="_sources_trimmed_v1", value=True))
    db.commit()
    return {"removed_sources": removed_sources, "removed_products": removed_products, "kept": len(keep)}




def enable_verified_sources(db: Session) -> int:
    """Enable the probed working sources. Idempotent and conservative: only sources
    that were never tried (status 'new') get enabled, so sources the admin disabled
    after a failed run stay disabled across restarts."""
    enabled = 0
    for name in VERIFIED_SOURCES:
        s = db.query(models.Source).filter(models.Source.name == name).first()
        if not s or s.enabled or s.status != "new":
            continue
        s.adapter = "generic"
        cfg = dict(s.config or {})
        cfg.setdefault("listing_url", s.url)
        cfg.setdefault("max_products", 2000)
        cfg.setdefault("max_pages", 20)
        s.config = cfg
        s.enabled = True
        enabled += 1
    if enabled:
        db.commit()
    return enabled


def purge_orphan_media(db: Session) -> dict:
    """One-time: delete stored scraped photos that no product or order refers to (frees database space)."""
    if db.query(models.Setting).filter(models.Setting.key == "_media_purged_v1").first():
        return {"skipped": True}
    from ..config import MEDIA_IN_DB
    from . import media_store

    deleted = 0
    if MEDIA_IN_DB:
        used: set[str] = set()
        for (imgs,) in db.query(models.Product.images).all():
            for i in imgs or []:
                if isinstance(i, str) and not i.startswith("http"):
                    used.add(media_store.clean_rel(i))
        for (img,) in db.query(models.OrderItem.image).all():
            if isinstance(img, str) and img and not img.startswith("http"):
                used.add(media_store.clean_rel(img))
        paths = [r[0] for r in db.query(models.MediaFile.path).filter(models.MediaFile.path.like("scraped/%")).all()]
        orphans = [x for x in paths if x not in used]
        for i in range(0, len(orphans), 300):
            chunk = orphans[i : i + 300]
            db.query(models.MediaFile).filter(models.MediaFile.path.in_(chunk)).delete(synchronize_session=False)
            deleted += len(chunk)
            db.commit()
    db.add(models.Setting(key="_media_purged_v1", value=True))
    db.commit()
    return {"deleted_files": deleted}


def ensure_seed(db: Session):
    seed_settings(db)
    _raise_scrape_limit(db)
    seed_admin(db)
    seed_categories(db)
    seed_sources(db)
    trim_sources(db)
    purge_orphan_media(db)
    # enable_verified_sources() is no longer called: sites you deactivate must stay deactivated.
    # Demo catalog seeding removed (real data only): seed_demo_products is no
    # longer called. The function is kept for reference/debugging but guarded
    # behind an explicit env flag.
    import os
    if os.getenv("SHOPEE_SEED_DEMO") == "1":
        seed_demo_products(db)
