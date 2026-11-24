"""Media storage: files on disk locally, rows in the database on serverless hosts (Vercel).

All paths are relative to the /media root, e.g. "scraped/12/abc.jpg".
"""
import mimetypes
from pathlib import Path

from .. import models
from ..config import MEDIA_DIR, MEDIA_IN_DB
from ..database import SessionLocal


def clean_rel(rel: str) -> str:
    rel = (rel or "").strip().lstrip("/")
    if rel.startswith("media/"):
        rel = rel[len("media/"):]
    parts = [p for p in rel.replace("\\", "/").split("/") if p not in ("", ".", "..")]
    return "/".join(parts)


def guess_type(rel: str) -> str:
    return mimetypes.guess_type(rel)[0] or "application/octet-stream"


def save(rel: str, data: bytes, content_type: str | None = None) -> str:
    """Store bytes, return the public URL path (/media/...)."""
    rel = clean_rel(rel)
    ctype = content_type or guess_type(rel)
    if MEDIA_IN_DB:
        db = SessionLocal()
        try:
            row = db.get(models.MediaFile, rel)
            if row:
                row.data, row.content_type = data, ctype
            else:
                db.add(models.MediaFile(path=rel, content_type=ctype, data=data))
            db.commit()
        finally:
            db.close()
    else:
        p = MEDIA_DIR / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(data)
    return "/media/" + rel


def load(rel: str) -> tuple[bytes, str] | None:
    """Return (bytes, content_type) or None. Checks the DB first, then disk."""
    rel = clean_rel(rel)
    if not rel:
        return None
    if MEDIA_IN_DB:
        db = SessionLocal()
        try:
            row = db.get(models.MediaFile, rel)
            if row:
                return bytes(row.data), row.content_type
        finally:
            db.close()
    p = (MEDIA_DIR / rel).resolve()
    try:
        p.relative_to(MEDIA_DIR.resolve())
    except ValueError:
        return None
    if p.is_file():
        return p.read_bytes(), guess_type(p.name)
    return None
