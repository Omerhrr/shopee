"""Auto-translation service for scraped Korean listings.

Pluggable providers - configure in Admin > Settings:
  - google_free (no API key required, uses the public Google Translate web endpoint)
  - papago  (Naver Clova, ideal for Korean)  keys: translate_api_key (X-NCP-APIGW-API-KEY-ID) + translate_api_secret
  - deepl   (auth key in translate_api_key, free/pro host)
  - google  (Cloud Translation v2 API key in translate_api_key)
  - none    -> scraped items stay in original Korean with a "translation pending" badge
"""
import httpx
from sqlalchemy.orm import Session

from .. import models
from ..deps import get_setting

TIMEOUT = 20.0
UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0 Safari/537.36"
)


def sanitize_dashes(text: str) -> str:
    """The house style bans em/en dashes - normalize them to plain hyphens."""
    return (text or "").replace("\u2014", "-").replace("\u2013", "-")


def _google_free(text: str, source_lang: str = "ko", target_lang: str = "en") -> str:
    """Public Google Translate web endpoint - no API key needed. Best-effort."""
    r = httpx.get(
        "https://translate.googleapis.com/translate_a/single",
        params={"client": "gtx", "sl": source_lang, "tl": target_lang, "dt": "t", "q": text[:4500]},
        headers={"User-Agent": UA, "Accept-Language": "en;q=0.9"},
        timeout=TIMEOUT,
    )
    r.raise_for_status()
    data = r.json()
    out = ""
    for seg in (data[0] or []):
        if seg and seg[0]:
            out += seg[0]
    return sanitize_dashes(out.strip())


def _papago(text: str, key: str, secret: str) -> str:
    r = httpx.post(
        "https://openapi.naver.com/v1/papago/n2mt",
        headers={"X-NCP-APIGW-API-KEY-ID": key, "X-NCP-APIGW-API-KEY": secret},
        data={"source": "ko", "target": "en", "text": text},
        timeout=TIMEOUT,
    )
    r.raise_for_status()
    return sanitize_dashes(r.json()["message"]["result"]["translatedText"])


def _deepl(text: str, key: str, host: str) -> str:
    url = (
        "https://api-free.deepl.com/v2/translate"
        if host == "free"
        else "https://api.deepl.com/v2/translate"
    )
    r = httpx.post(
        url,
        headers={"Authorization": f"DeepL-Auth-Key {key}"},
        data={"text": text, "source_lang": "KO", "target_lang": "EN"},
        timeout=TIMEOUT,
    )
    r.raise_for_status()
    return sanitize_dashes(r.json()["translations"][0]["text"])


def _google(text: str, key: str) -> str:
    r = httpx.post(
        "https://translation.googleapis.com/language/translate/v2",
        params={"key": key},
        data={"q": text, "source": "ko", "target": "en", "format": "text"},
        timeout=TIMEOUT,
    )
    r.raise_for_status()
    return sanitize_dashes(r.json()["data"]["translations"][0]["translatedText"])


def translate_text(text: str, db: Session | None = None) -> str:
    """Translate Korean -> English using the configured provider. Raises on failure."""
    provider = get_setting(db, "translate_provider", "none") if db else "none"
    text = (text or "").strip()
    if not text:
        return ""
    if provider == "google_free":
        return _google_free(text)
    if provider == "papago":
        return _papago(text, get_setting(db, "translate_api_key", ""), get_setting(db, "translate_api_secret", ""))
    if provider == "deepl":
        return _deepl(text, get_setting(db, "translate_api_key", ""), get_setting(db, "translate_deepl_host", "free"))
    if provider == "google":
        return _google(text, get_setting(db, "translate_api_key", ""))
    raise RuntimeError("No translation provider configured (Admin > Settings > Translation)")


def test_provider(db: Session) -> dict:
    """Used by the admin 'Test translation' button."""
    provider = get_setting(db, "translate_provider", "none")
    if provider == "none":
        return {"ok": False, "provider": provider, "error": "No provider configured"}
    try:
        result = translate_text("여성용 데일리 크로스백, 방수 소재", db)
        return {"ok": True, "provider": provider, "sample": result}
    except Exception as e:
        return {"ok": False, "provider": provider, "error": str(e)[:300]}


def translate_product(db: Session, p: models.Product) -> bool:
    """Translate title/description of a single product. Returns True on success."""
    if p.original_lang != "ko":
        p.translation_status = "none"
        return True
    title = translate_text(p.title_ko, db)
    desc = translate_text(p.desc_ko or "", db)
    if not title:
        raise RuntimeError("empty translation result")
    p.title_en = title[:290]
    p.desc_en = desc or None
    p.translation_status = "done"
    return True


def run_pending_translations(db: Session, limit: int = 25) -> dict:
    """Translate all pending products (called by scheduler and admin button)."""
    provider = get_setting(db, "translate_provider", "none")
    if provider == "none":
        return {"skipped": True, "reason": "No translation provider configured", "translated": 0, "failed": 0}

    pending = (
        db.query(models.Product)
        .filter(models.Product.translation_status == "pending", models.Product.original_lang == "ko")
        .order_by(models.Product.created_at.desc())
        .limit(limit)
        .all()
    )
    ok = fail = 0
    for p in pending:
        try:
            translate_product(db, p)
            ok += 1
        except Exception:
            p.translation_status = "failed"
            fail += 1
        db.commit()
    return {"skipped": False, "translated": ok, "failed": fail, "remaining": pending_count(db)}


def pending_count(db: Session) -> int:
    return (
        db.query(models.Product)
        .filter(models.Product.translation_status == "pending", models.Product.original_lang == "ko")
        .count()
    )
