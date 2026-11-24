"""Auto-translation service for scraped Korean listings.

Pluggable providers - configure in Admin > Settings:
  - google_free (no API key required, uses the public Google Translate web endpoint)
  - papago  (Naver Clova, ideal for Korean)  keys: translate_api_key (X-NCP-APIGW-API-KEY-ID) + translate_api_secret
  - deepl   (auth key in translate_api_key, free/pro host)
  - google  (Cloud Translation v2 API key in translate_api_key)
  - none    -> scraped items stay in original Korean with a "translation pending" badge
"""
import re

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


def _google_free(text: str, src: str = "ko", tgt: str = "en") -> str:
    """Public Google Translate web endpoint - no API key needed. Best-effort."""
    r = httpx.get(
        "https://translate.googleapis.com/translate_a/single",
        params={"client": "gtx", "sl": src, "tl": tgt, "dt": "t", "q": text[:4500]},
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


def _papago(text: str, key: str, secret: str, src: str = "ko", tgt: str = "en") -> str:
    r = httpx.post(
        "https://openapi.naver.com/v1/papago/n2mt",
        headers={"X-NCP-APIGW-API-KEY-ID": key, "X-NCP-APIGW-API-KEY": secret},
        data={"source": src, "target": tgt, "text": text},
        timeout=TIMEOUT,
    )
    r.raise_for_status()
    return sanitize_dashes(r.json()["message"]["result"]["translatedText"])


def _deepl(text: str, key: str, host: str, src: str = "ko", tgt: str = "en") -> str:
    url = (
        "https://api-free.deepl.com/v2/translate"
        if host == "free"
        else "https://api.deepl.com/v2/translate"
    )
    r = httpx.post(
        url,
        headers={"Authorization": f"DeepL-Auth-Key {key}"},
        data={"text": text, "source_lang": src.upper(), "target_lang": "EN-US" if tgt == "en" else tgt.upper()},
        timeout=TIMEOUT,
    )
    r.raise_for_status()
    return sanitize_dashes(r.json()["translations"][0]["text"])


def _google(text: str, key: str, src: str = "ko", tgt: str = "en") -> str:
    r = httpx.post(
        "https://translation.googleapis.com/language/translate/v2",
        params={"key": key},
        data={"q": text, "source": src, "target": tgt, "format": "text"},
        timeout=TIMEOUT,
    )
    r.raise_for_status()
    return sanitize_dashes(r.json()["data"]["translations"][0]["translatedText"])


def _chunks(text: str, size: int = 3000) -> list[str]:
    """Split long text on whitespace/sentence boundaries so providers never truncate it."""
    out, cur = [], ""
    for part in re.split(r"(?<=[.!?。\n])\s*", text):
        if len(cur) + len(part) + 1 > size and cur:
            out.append(cur)
            cur = ""
        while len(part) > size:  # no boundary at all: hard split
            out.append(part[:size])
            part = part[size:]
        cur = (cur + " " + part).strip()
    if cur:
        out.append(cur)
    return out


def translate_text(text: str, db: Session | None = None, src: str = "ko", tgt: str = "en") -> str:
    """Translate src -> tgt (ko/en) with the configured provider. Raises on failure."""
    provider = get_setting(db, "translate_provider", "none") if db else "none"
    text = (text or "").strip()
    if not text:
        return ""
    if provider not in ("google_free", "papago", "deepl", "google"):
        raise RuntimeError("No translation provider configured (Admin > Settings > Translation)")
    key = get_setting(db, "translate_api_key", "")
    secret = get_setting(db, "translate_api_secret", "")
    host = get_setting(db, "translate_deepl_host", "free")

    def one(chunk: str) -> str:
        if provider == "google_free":
            return _google_free(chunk, src, tgt)
        if provider == "papago":
            return _papago(chunk, key, secret, src, tgt)
        if provider == "deepl":
            return _deepl(chunk, key, host, src, tgt)
        return _google(chunk, key, src, tgt)

    return " ".join(one(c) for c in _chunks(text))


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


def _has_hangul(text: str) -> bool:
    return bool(re.search(r"[\uac00-\ud7a3]", text or ""))


def translate_product(db_or_none, p: models.Product) -> bool:
    """Fill the MISSING language side of a product (never overwrites text someone wrote).
    Korean-original items get title_en/desc_en; English-original items get title_ko/desc_ko."""
    db = db_or_none
    src = "en" if p.original_lang == "en" else "ko"
    tgt = "ko" if src == "en" else "en"
    t_src, d_src = (p.title_en or "", p.desc_en or "") if src == "en" else (p.title_ko or "", p.desc_ko or "")
    t_tgt, d_tgt = (p.title_ko or "", p.desc_ko or "") if tgt == "ko" else (p.title_en or "", p.desc_en or "")
    if not t_src.strip():  # nothing to translate from: fall back to whichever side has a title
        src, tgt = ("ko", "en") if (p.title_ko or "").strip() else ("en", "ko")
        t_src, d_src = (p.title_ko or "", p.desc_ko or "") if src == "ko" else (p.title_en or "", p.desc_en or "")
        t_tgt, d_tgt = (p.title_en or "", p.desc_en or "") if tgt == "en" else (p.title_ko or "", p.desc_ko or "")
    if t_src.strip() and not t_tgt.strip():
        t_tgt = translate_text(t_src, db, src, tgt)[:290]
        if not t_tgt:
            raise RuntimeError("empty translation result")
    if d_src.strip() and not d_tgt.strip():
        d_tgt = translate_text(d_src, db, src, tgt)
    # English side that still contains Hangul = earlier fallback copy, redo it
    if tgt == "en" and _has_hangul(t_tgt):
        t_tgt = translate_text(t_src, db, "ko", "en")[:290]
    if tgt == "en":
        p.title_en, p.desc_en = t_tgt or None, d_tgt or None
    else:
        p.title_ko, p.desc_ko = t_tgt, d_tgt
    p.translation_status = "done"
    return True


def translate_source_labels(db: Session, limit: int = 20) -> int:
    """Store English versions of supplier name / category / product hints in source.config
    (no schema change): config.name_en, config.category_hint_en, config.products_hint_en."""
    provider = get_setting(db, "translate_provider", "none")
    if provider == "none":
        return 0
    done = 0
    for s in db.query(models.Source).all():
        cfg = dict(s.config or {})
        todo = [(f, getattr(s, f)) for f in ("name", "category_hint", "products_hint")
                if _has_hangul(getattr(s, f) or "") and not cfg.get(f + "_en")]
        if not todo:
            continue
        try:
            for field, val in todo:
                cfg[field + "_en"] = translate_text(val, db, "ko", "en")[:150]
            s.config = cfg
            db.commit()
            done += 1
        except Exception:
            db.rollback()
            break
        if done >= limit:
            break
    return done


def run_pending_translations(db: Session, limit: int = 25) -> dict:
    """Translate pending/failed products (scheduler, cron and admin button)."""
    provider = get_setting(db, "translate_provider", "none")
    if provider == "none":
        return {"skipped": True, "reason": "No translation provider configured", "translated": 0, "failed": 0}

    pending = (
        db.query(models.Product)
        .filter(models.Product.translation_status.in_(("pending", "failed")))
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
    labels = translate_source_labels(db)
    return {"skipped": False, "translated": ok, "failed": fail, "sources_translated": labels, "remaining": pending_count(db)}


def pending_count(db: Session) -> int:
    return db.query(models.Product).filter(models.Product.translation_status.in_(("pending", "failed"))).count()
