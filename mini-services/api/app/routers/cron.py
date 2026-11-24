"""Vercel Cron entrypoint (no always-on scheduler on serverless).

Vercel calls GET /api/cron/run with `Authorization: Bearer $CRON_SECRET`.
Scrapes enabled sources (time-boxed, least recently scraped first), then translates pending items.
"""
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
