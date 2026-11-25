"""Public image relay for supplier images (signed links only: it cannot be used to fetch arbitrary URLs)."""
import hmac
from urllib.parse import unquote

from fastapi import APIRouter
from fastapi.responses import Response

from ..services.images import fetch_remote, sign

router = APIRouter(tags=["images"])

_PLACEHOLDER = (
    b'<svg xmlns="http://www.w3.org/2000/svg" width="400" height="400" viewBox="0 0 400 400">'
    b'<rect width="400" height="400" fill="#f1f5f9"/><path d="M120 270l50-60 40 45 30-35 40 50z" fill="#cbd5e1"/>'
    b'<circle cx="150" cy="150" r="22" fill="#cbd5e1"/></svg>'
)
_SAFE_HEADERS = {"X-Content-Type-Options": "nosniff", "Content-Security-Policy": "default-src 'none'; sandbox"}


@router.get("/api/img")
def image_relay(u: str = "", s: str = ""):
    url = unquote(u or "")
    if not url or not hmac.compare_digest(sign(url), s or ""):
        return Response(status_code=403)
    hit = fetch_remote(url, timeout=10.0, allow_svg=True)
    if not hit:
        return Response(_PLACEHOLDER, media_type="image/svg+xml", headers={**_SAFE_HEADERS, "Cache-Control": "public, max-age=300"})
    blob, ct = hit
    return Response(
        blob,
        media_type=ct,
        headers={**_SAFE_HEADERS, "Cache-Control": "public, max-age=86400, s-maxage=2592000, stale-while-revalidate=86400"},
    )
