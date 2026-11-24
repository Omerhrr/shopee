"""Record probe outcomes on each source so the admin panel shows the real reason
a site is not scraped: dead / js-rendered / members-only etc.
Parses /tmp/probe-full.log (from expand_sources.py probe)."""
import re
import sys

sys.path.insert(0, "/home/z/my-project/mini-services/api")

from app.database import SessionLocal
from app import models

log = open("/tmp/probe-full.log", encoding="utf-8").read()

nolinks = {int(m) for m in re.findall(r"NOLINKS\s+\[(\d+)\]", log)}
unreach = {int(m) for m in re.findall(r"UNREACH\s+\[(\d+)\]", log)}

MSG_NOLINKS = "Reachable, but the listing page is JavaScript-rendered / uses a custom layout - no parseable product links. Needs a dedicated adapter."
MSG_UNREACH = "Site is not reachable (expired domain, DNS failure, timeout, or HTTP 403/404) - cannot be scraped."

db = SessionLocal()
try:
    a = db.query(models.Source).filter(models.Source.id.in_(nolinks)).update(
        {models.Source.status: "error", models.Source.enabled: False, models.Source.last_error: MSG_NOLINKS},
        synchronize_session=False,
    )
    b = db.query(models.Source).filter(models.Source.id.in_(unreach)).update(
        {models.Source.status: "error", models.Source.enabled: False, models.Source.last_error: MSG_UNREACH},
        synchronize_session=False,
    )
    db.commit()
    counts = {}
    for status, n in db.query(models.Source.status, func_count := models.Source.id).group_by(models.Source.status):
        pass
    rows = db.query(models.Source.status, models.Source.enabled).all()
    for status, enabled in rows:
        key = f"{status}{'/enabled' if enabled else '/disabled'}"
        counts[key] = counts.get(key, 0) + 1
    print("updated nolinks:", a, "unreachable:", b)
    print("final counts:", counts)
finally:
    db.close()
