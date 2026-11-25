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


_blocked_until = 0.0  # circuit breaker: after a 429 stop hammering the free endpoint for a while


class RateLimited(RuntimeError):
    pass


def _google_free(text: str, src: str = "ko", tgt: str = "en") -> str:
    """Public Google Translate web endpoint - no API key needed. Best-effort, shared IPs get 429."""
    import time

    global _blocked_until
    if time.time() < _blocked_until:
        raise RateLimited("Google free translate is rate limiting this server (429). Add a Papago, DeepL or Google API key in Admin > Settings > Translation.")
    r = None
    for attempt in range(3):
        r = httpx.get(
            "https://translate.googleapis.com/translate_a/single",
            params={"client": "gtx", "sl": src, "tl": tgt, "dt": "t", "q": text[:4500]},
            headers={"User-Agent": UA, "Accept-Language": "en;q=0.9"},
            timeout=TIMEOUT,
        )
        if r.status_code not in (429, 503):
            break
        time.sleep(1.5 * (attempt + 1))
    if r.status_code == 429:
        _blocked_until = time.time() + 90
        raise RateLimited("Google free translate returned 429 Too Many Requests. Add a Papago, DeepL or Google API key in Admin > Settings > Translation.")
    r.raise_for_status()
    data = r.json()
    out = ""
    for seg in (data[0] or []):
        if seg and seg[0]:
            out += seg[0]
    return sanitize_dashes(out.strip())


_edge_token_cache = {"token": "", "exp": 0.0}


def _edge(text: str, src: str = "ko", tgt: str = "en") -> str:
    """Microsoft Translator through the public Edge-browser endpoint: no account, no key.
    (Unofficial but long-stable; a token is fetched from edge.microsoft.com and cached.)"""
    import time

    if not _edge_token_cache["token"] or time.time() > _edge_token_cache["exp"]:
        tr = httpx.get("https://edge.microsoft.com/translate/auth", headers={"User-Agent": UA}, timeout=TIMEOUT)
        tr.raise_for_status()
        _edge_token_cache.update(token=tr.text.strip(), exp=time.time() + 8 * 60)
    r = httpx.post(
        "https://api-edge.cognitive.microsofttranslator.com/translate",
        params={"from": src, "to": tgt, "api-version": "3.0"},
        headers={"Authorization": f"Bearer {_edge_token_cache['token']}", "User-Agent": UA},
        json=[{"Text": text}],
        timeout=TIMEOUT,
    )
    if r.status_code == 401:  # token expired early: refresh once
        _edge_token_cache["exp"] = 0
        raise RuntimeError("Microsoft token rejected, retry")
    r.raise_for_status()
    return sanitize_dashes(r.json()[0]["translations"][0]["text"].strip())


def _libre(text: str, url: str, key: str = "", src: str = "ko", tgt: str = "en") -> str:
    """LibreTranslate (self-hosted, or any public instance that does not need a key)."""
    if not url:
        raise RuntimeError("LibreTranslate server URL is empty (Admin > Settings > Translation)")
    payload = {"q": text, "source": src, "target": tgt, "format": "text"}
    if key:
        payload["api_key"] = key
    r = httpx.post(url.rstrip("/") + "/translate", json=payload, timeout=TIMEOUT)
    r.raise_for_status()
    return sanitize_dashes(r.json()["translatedText"].strip())


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


def _gemini(text: str, key: str, src: str = "ko", tgt: str = "en") -> str:
    """Google Gemini (free tier key from Google AI Studio, no card needed)."""
    import time

    if not key:
        raise RuntimeError("Gemini API key is empty (Admin > Settings > Translation)")
    names = {"ko": "Korean", "en": "English"}
    prompt = (
        f"Translate the following {names.get(src, src)} text to {names.get(tgt, tgt)}. "
        "Keep the same number of lines and line order. Output only the translation, no notes, no quotes.\n\n" + text
    )
    last = None
    for attempt in range(3):
        r = httpx.post(
            "https://generativelanguage.googleapis.com/v1beta/models/gemini-flash-latest:generateContent",
            headers={"x-goog-api-key": key, "Content-Type": "application/json"},
            json={"contents": [{"parts": [{"text": prompt}]}], "generationConfig": {"temperature": 0}},
            timeout=60,
        )
        if r.status_code == 429:
            last = r
            time.sleep(2 + attempt * 3)
            continue
        if r.status_code >= 400:
            raise RuntimeError(f"Gemini error {r.status_code}: {r.text[:200]}")
        parts = r.json()["candidates"][0]["content"]["parts"]
        return sanitize_dashes("".join(x.get("text", "") for x in parts).strip())
    raise RuntimeError("Gemini free limit reached (429). Wait a minute or try again tomorrow.")


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


def load_cfg(db: Session) -> dict:
    return {
        "provider": get_setting(db, "translate_provider", "none"),
        "key": get_setting(db, "translate_api_key", ""),
        "secret": get_setting(db, "translate_api_secret", ""),
        "host": get_setting(db, "translate_deepl_host", "free"),
        "libre_url": get_setting(db, "translate_libre_url", ""),
    }


def translate_text(text: str, db: Session | None = None, src: str = "ko", tgt: str = "en", cfg: dict | None = None) -> str:
    """Translate src -> tgt (ko/en) with the configured provider. Raises on failure.
    Pass cfg (from load_cfg) when calling from worker threads: sessions are not thread-safe."""
    if cfg is None:
        cfg = load_cfg(db) if db else {"provider": "none"}
    provider = cfg.get("provider", "none")
    text = (text or "").strip()
    if not text:
        return ""
    if provider not in ("google_free", "edge", "libre", "gemini", "papago", "deepl", "google"):
        raise RuntimeError("No translation provider configured (Admin > Settings > Translation)")
    key, secret, host = cfg.get("key", ""), cfg.get("secret", ""), cfg.get("host", "free")

    def one(chunk: str) -> str:
        if provider == "google_free":
            # Google's free endpoint 429s on shared hosts like Vercel: fall back to Microsoft automatically
            try:
                return _google_free(chunk, src, tgt)
            except Exception as e1:
                try:
                    return _edge(chunk, src, tgt)
                except Exception as e2:
                    raise RuntimeError(f"Google failed: {str(e1)[:120]} | Microsoft fallback failed: {type(e2).__name__}: {str(e2)[:160]}")
        if provider == "edge":
            try:
                return _edge(chunk, src, tgt)
            except Exception as e1:
                try:
                    return _google_free(chunk, src, tgt)
                except Exception as e2:
                    raise RuntimeError(f"Microsoft failed: {type(e1).__name__}: {str(e1)[:160]} | Google fallback failed: {str(e2)[:120]}")
        if provider == "libre":
            return _libre(chunk, cfg.get("libre_url", ""), key, src, tgt)
        if provider == "gemini":
            return _gemini(chunk, key, src, tgt)
        if provider == "papago":
            return _papago(chunk, key, secret, src, tgt)
        if provider == "deepl":
            return _deepl(chunk, key, host, src, tgt)
        return _google(chunk, key, src, tgt)

    if len(text) <= 3000:
        return one(text)  # keeps newlines intact (used for batched titles)
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


def _translate_batch(texts: list[str], src: str, tgt: str, cfg: dict) -> list[str]:
    """Translate several short texts in ONE request (newline separated). If the provider changes
    the line count, fall back to one request per text so titles never get mixed up."""
    flat = [" ".join(t.split()) for t in texts]
    if len(flat) == 1:
        return [translate_text(flat[0], None, src, tgt, cfg)]
    joined = translate_text("\n".join(flat), None, src, tgt, cfg)
    lines = [ln.strip() for ln in joined.split("\n")]
    if len(lines) == len(flat) and all(lines):
        return lines
    return [translate_text(t, None, src, tgt, cfg) for t in flat]


def ensure_translated(db: Session, prods: list, lang: str, budget_s: float = 25.0, max_items: int = 300) -> int:
    """Make sure each product has title/description in `lang` ("en" or "ko") BEFORE it is shown or
    exported. Missing sides are machine-translated in parallel and saved. Best effort: a failure or
    the time budget leaves the product untouched (it is retried later). Returns products updated."""
    import time
    from concurrent.futures import ThreadPoolExecutor, wait

    if lang not in ("en", "ko"):
        return 0
    cfg = load_cfg(db)
    if cfg["provider"] == "none":
        return 0
    other = "ko" if lang == "en" else "en"

    def missing(txt, p=None) -> bool:
        txt = (txt or "").strip()
        if not txt:
            return True
        # leftover Hangul (untranslatable brand names...) only counts while not yet marked done,
        # otherwise the same product would be re-translated on every request
        return lang == "en" and _has_hangul(txt) and not (p is not None and p.translation_status == "done")

    jobs = []  # (product, field, source_text)
    for p in prods:
        if len(jobs) >= max_items * 2:
            break
        t_have, d_have = getattr(p, f"title_{lang}"), getattr(p, f"desc_{lang}")
        t_src, d_src = getattr(p, f"title_{other}") or "", getattr(p, f"desc_{other}") or ""
        if missing(t_have, p) and t_src.strip():
            jobs.append((p, "title", t_src))
        if missing(d_have, p) and d_src.strip():
            jobs.append((p, "desc", d_src))
    if not jobs:
        return 0

    started = time.time()
    results: dict = {}
    ex = ThreadPoolExecutor(max_workers=3)  # gentle: free endpoints rate-limit hard
    futs = {}
    # titles are short: send up to 15 per request (one per line) and split the answer back
    titles = [(p.id, txt) for p, field, txt in jobs if field == "title"]
    for i in range(0, len(titles), 15):
        group = titles[i:i + 15]
        futs[ex.submit(_translate_batch, [t for _, t in group], other, lang, cfg)] = ("batch", [pid for pid, _ in group])
    for p, field, src_txt in jobs:
        if field == "desc":
            futs[ex.submit(translate_text, src_txt, None, other, lang, cfg)] = (p.id, "desc")
    done, _ = wait(list(futs), timeout=max(1.0, budget_s - (time.time() - started)))
    for fu in done:
        key = futs[fu]
        try:
            res = fu.result()
        except Exception:
            continue
        if key[0] == "batch":
            for pid, txt in zip(key[1], res):
                if txt:
                    results[(pid, "title")] = txt
        else:
            results[key] = res
    ex.shutdown(wait=False, cancel_futures=True)

    changed = 0
    for p in prods:
        touched = False
        t = results.get((p.id, "title"))
        d = results.get((p.id, "desc"))
        if t:
            setattr(p, f"title_{lang}", t[:290] if lang == "en" else t[:290])
            touched = True
        if d:
            setattr(p, f"desc_{lang}", d)
            touched = True
        if touched:
            ok_t = bool((getattr(p, f"title_{lang}") or "").strip())
            ok_d = (not (getattr(p, f"desc_{other}") or "").strip()) or bool((getattr(p, f"desc_{lang}") or "").strip())
            if ok_t and ok_d:
                p.translation_status = "done"
            changed += 1
    if changed:
        db.commit()
    return changed
