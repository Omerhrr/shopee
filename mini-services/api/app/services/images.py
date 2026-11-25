"""Remote product images: we store only the supplier's image URL, never the file.

- proxy_url(): what the storefront / downloader page shows. A signed link to /api/img, which streams the
  image from the supplier on demand (so hotlink blocks and http-on-https problems do not matter) and is
  cached by the CDN, so repeat views cost nothing and nothing is stored in the database.
- fetch_download_images(): used only when someone downloads a ZIP or Excel: the files are fetched at that moment.
"""
import hashlib
import hmac
import io
import ipaddress
import os
import socket
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import parse_qs, quote, urlparse

import httpx

from . import media_store
from ..config import SECRET_KEY

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"
MAX_BYTES = 8 * 1024 * 1024
ALLOWED_EXT = {".jpg", ".jpeg", ".png", ".webp"}
EXT_BY_TYPE = {"image/jpeg": ".jpg", "image/jpg": ".jpg", "image/png": ".png", "image/webp": ".webp"}


def is_remote(u) -> bool:
    return isinstance(u, str) and u.strip().lower().startswith(("http://", "https://"))


def sign(url: str) -> str:
    return hmac.new(SECRET_KEY.encode(), url.encode(), hashlib.sha256).hexdigest()[:20]


def proxy_path(url: str) -> str:
    return f"/api/img?u={quote(url, safe='')}&s={sign(url)}"


def proxy_url(u):
    """Remote image URL -> our signed relay path. Local /media paths and anything else are returned unchanged."""
    return proxy_path(u.strip()) if is_remote(u) else u


def unproxy(u):
    """Reverse of proxy_url (an edit form sends back what it was shown)."""
    if isinstance(u, str) and u.startswith("/api/img?"):
        q = parse_qs(urlparse(u).query)
        if q.get("u"):
            return q["u"][0]
    return u


def _public_host(host: str) -> bool:
    try:
        for fam, _, _, _, sa in socket.getaddrinfo(host, None):
            ip = ipaddress.ip_address(sa[0])
            if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast or ip.is_unspecified:
                return False
        return True
    except Exception:
        return False


def _looks_svg(r, ct: str, url: str) -> bool:
    if "svg" in ct:
        return True
    head = r.content[:300].lstrip().lower()
    return (url.split("?")[0].lower().endswith(".svg") or ct in ("text/xml", "application/xml", "text/plain", "application/octet-stream")) and (b"<svg" in head or (head.startswith(b"<?xml") and b"<svg" in r.content[:1500].lower()))


def clean_svg(blob: bytes) -> bytes:
    """Defence in depth: drop scripts, event handlers and foreign objects (the relay also sends a sandbox CSP)."""
    import re

    t = blob.decode("utf-8", "ignore")
    t = re.sub(r"<script\b.*?</script\s*>", "", t, flags=re.I | re.S)
    t = re.sub(r"<foreignObject\b.*?</foreignObject\s*>", "", t, flags=re.I | re.S)
    t = re.sub(r"\son\w+\s*=\s*(\"[^\"]*\"|'[^']*'|[^\s>]+)", "", t, flags=re.I)
    t = re.sub(r"(href\s*=\s*[\"'])\s*javascript:[^\"']*", r"\1#", t, flags=re.I)
    return t.encode("utf-8")


def fetch_remote(url: str, timeout: float = 12.0, allow_svg: bool = False) -> tuple[bytes, str] | None:
    """Fetch one image: http(s) only, public hosts only, redirects re-checked, size and type limited."""
    cur = url.strip()
    try:
        with httpx.Client(headers={"User-Agent": UA, "Accept": "image/*,*/*"}, timeout=timeout, follow_redirects=False) as c:
            for _ in range(4):
                u = urlparse(cur)
                if u.scheme not in ("http", "https") or not u.hostname or u.port not in (None, 80, 443) or not _public_host(u.hostname):
                    return None
                r = c.get(cur, headers={"Referer": f"{u.scheme}://{u.netloc}/"})
                if r.status_code in (301, 302, 303, 307, 308) and r.headers.get("location"):
                    cur = str(httpx.URL(cur).join(r.headers["location"]))
                    continue
                ct = (r.headers.get("content-type") or "").split(";")[0].strip().lower()
                if r.status_code != 200:
                    return None
                if _looks_svg(r, ct, cur):
                    if not allow_svg or len(r.content) > MAX_BYTES:
                        return None
                    return clean_svg(r.content), "image/svg+xml"
                if not ct.startswith("image/"):
                    return None
                if len(r.content) < 400 or len(r.content) > MAX_BYTES:
                    return None
                return r.content, ct
    except Exception:
        return None
    return None


def _normalise(blob: bytes, ct: str) -> tuple[bytes, str] | None:
    """Shopee-friendly file: keep jpg/png/webp as they are, convert anything else (gif, bmp, avif...) to JPEG."""
    ext = EXT_BY_TYPE.get(ct)
    if ext:
        return blob, ext
    try:
        from PIL import Image

        im = Image.open(io.BytesIO(blob)).convert("RGB")
        buf = io.BytesIO()
        im.save(buf, "JPEG", quality=88)
        return buf.getvalue(), ".jpg"
    except Exception:
        return None


def fetch_download_images(images: list, limit: int = 5) -> list[tuple[bytes, str]]:
    """[(bytes, ext)] for a product, from local storage (older products) or fetched live from the supplier."""
    out: list[tuple[bytes, str]] = []
    seen: set[str] = set()
    for e in images or []:
        if len(out) >= limit:
            break
        if not isinstance(e, str) or not e.strip():
            continue
        e = unproxy(e.strip())
        if e in seen:
            continue
        seen.add(e)
        if is_remote(e):
            hit = fetch_remote(e)
            norm = _normalise(*hit) if hit else None
            if norm:
                out.append(norm)
        else:
            rel = media_store.clean_rel(e)
            ext = os.path.splitext(rel)[1].lower()
            if ext not in ALLOWED_EXT:
                continue
            hit = media_store.load(rel)
            if hit and len(hit[0]) > 512:
                out.append((hit[0], ".jpg" if ext == ".jpeg" else ext))
    return out


def fetch_download_images_many(image_lists: list[list], limit: int = 5, workers: int = 8) -> list[list[tuple[bytes, str]]]:
    """Same for many products at once (parallel), keeping order."""
    with ThreadPoolExecutor(max_workers=workers) as pool:
        return list(pool.map(lambda lst: fetch_download_images(lst, limit), image_lists))
