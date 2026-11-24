"""Background scheduler: periodic scraping of enabled sources + translation runs."""
import threading

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger

from ..database import SessionLocal
from .scraper import scrape_all_enabled
from .translator import run_pending_translations

_scheduler: BackgroundScheduler | None = None
_lock = threading.Lock()


def _job_scrape():
    db = SessionLocal()
    try:
        from ..deps import get_setting

        if not get_setting(db, "scrape_enabled", True):
            return
        scrape_all_enabled(db, trigger="schedule")
    except Exception:
        pass
    finally:
        db.close()


def _job_translate():
    db = SessionLocal()
    try:
        run_pending_translations(db, limit=20)
    except Exception:
        pass
    finally:
        db.close()


def _interval_minutes(db) -> int:
    from ..deps import get_setting

    return max(5, int(get_setting(db, "scrape_interval_minutes", 360) or 360))


def start_scheduler():
    global _scheduler
    with _lock:
        if _scheduler is not None:
            return _scheduler
        db = SessionLocal()
        minutes = _interval_minutes(db)
        db.close()
        _scheduler = BackgroundScheduler(timezone="UTC")
        _scheduler.add_job(_job_scrape, IntervalTrigger(minutes=minutes), id="scrape_all", replace_existing=True)
        _scheduler.add_job(_job_translate, IntervalTrigger(minutes=15), id="translate_pending", replace_existing=True)
        _scheduler.start()
        return _scheduler


def reschedule_scrape():
    """Called after admin changes scraping settings."""
    global _scheduler
    if _scheduler is None:
        return
    db = SessionLocal()
    try:
        minutes = _interval_minutes(db)
        enabled = bool(get_setting_safe(db, "scrape_enabled", True))
        if enabled:
            _scheduler.add_job(
                _job_scrape, IntervalTrigger(minutes=minutes), id="scrape_all", replace_existing=True
            )
        else:
            _scheduler.remove_job("scrape_all")
    except Exception:
        pass
    finally:
        db.close()


def get_setting_safe(db, key, default):
    from ..deps import get_setting

    return get_setting(db, key, default)


def next_run_times() -> dict:
    if _scheduler is None:
        return {}
    jobs = {j.id: str(j.next_run_time) if j.next_run_time else None for j in _scheduler.get_jobs()}
    return jobs
