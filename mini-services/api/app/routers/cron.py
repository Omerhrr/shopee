"""Vercel Cron entrypoint (no always-on scheduler on serverless).

Vercel calls GET /api/cron/run with `Authorization: Bearer $CRON_SECRET`.
Scrapes enabled sources (time-boxed, least recently scraped first), then translates pending items.
"""
import os
import time

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from ..config import CRON_SECRET
from ..database import get_db
from ..deps import get_setting
from ..services.scraper import scrape_all_enabled
from ..services.translator import run_pending_translations

router = APIRouter(prefix="/api/cron", tags=["cron"])

TIME_BUDGET_S = 240  # stay under the 300 s function limit


@router.get("/run")
def run(request: Request, db: Session = Depends(get_db)):
    if not CRON_SECRET or request.headers.get("Authorization") != f"Bearer {CRON_SECRET}":
        raise HTTPException(401, "Unauthorized")
    started = time.time()
    scraped = []
    if get_setting(db, "scrape_enabled", True):
        scraped = scrape_all_enabled(db, trigger="schedule", deadline=started + TIME_BUDGET_S)
    translated = run_pending_translations(db, limit=20) if time.time() - started < TIME_BUDGET_S + 20 else {"skipped": True}
    return {"ok": True, "seconds": round(time.time() - started), "scraped": scraped, "translated": translated}


@router.get("/admin-check")
def admin_check(request: Request, key: str = "", db: Session = Depends(get_db)):
    """Login diagnostics, protected by CRON_SECRET (Bearer header or ?key=). Shows no secrets."""
    from .. import models
    from ..config import SEED_ADMIN_EMAIL, SEED_ADMIN_PASSWORD
    from ..security import verify_password

    if not CRON_SECRET or (request.headers.get("Authorization") != f"Bearer {CRON_SECRET}" and key != CRON_SECRET):
        raise HTTPException(401, "Unauthorized")

    def mask(e: str) -> str:
        n, _, d = e.partition("@")
        return (n[:2] + "***@" + d) if d else e[:2] + "***"

    email = SEED_ADMIN_EMAIL.strip().lower()
    user = db.query(models.User).filter(models.User.email == email).first()
    return {
        "deployed_commit": (os.getenv("VERCEL_GIT_COMMIT_SHA") or "")[:7],
        "env_email_seen": mask(SEED_ADMIN_EMAIL),
        "env_email_has_whitespace_or_quotes": SEED_ADMIN_EMAIL != SEED_ADMIN_EMAIL.strip() or SEED_ADMIN_EMAIL.strip().startswith(("'", '"')),
        "env_password_length": len(SEED_ADMIN_PASSWORD),
        "env_password_has_whitespace_or_quotes": SEED_ADMIN_PASSWORD != SEED_ADMIN_PASSWORD.strip() or SEED_ADMIN_PASSWORD.startswith(("'", '"')),
        "reset_flag": os.getenv("SHOPEE_ADMIN_RESET") == "1",
        "admin_exists": bool(user),
        "env_password_matches_stored": bool(user and verify_password(SEED_ADMIN_PASSWORD, user.password_hash)),
        "all_admin_emails": [mask(u.email) for u in db.query(models.User).all()],
    }
