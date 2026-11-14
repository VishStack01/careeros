"""Job alert emails: an opt-in digest of the roles matched since the last one.

Off unless the person turns it on in Settings ("alerts": "daily" or "weekly"). Each digest lists up to
ten new roles that passed their filters, best fit first, each with the company's own application link.
Nothing is sent when there's nothing new. Turning alerts off is one switch in Settings, and every
email says where it is.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from . import repo
from .db import Database

EVERY = {"daily": timedelta(hours=23), "weekly": timedelta(days=6, hours=23)}
MAX_ROLES = 10


def _ts(s: str) -> datetime | None:
    try:
        d = datetime.fromisoformat(str(s).replace("Z", "+00:00"))
        return d if d.tzinfo else d.replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def _score(d: dict) -> float:
    ev = d.get("evaluation") or {}
    try:
        return float(d.get("scoreOverride") or ev.get("score") or d.get("score") or 0)
    except (TypeError, ValueError):
        return 0.0


def digest(name: str, roles: list[dict], period: str, public_url: str) -> tuple[str, str]:
    n = len(roles)
    subject = f"{n} new {'role' if n == 1 else 'roles'} for you on Propelo"
    lines = [f"Hi {name}," if name else "Hi,", "",
             f"{n} new {'role' if n == 1 else 'roles'} passed your filters since your last {'daily' if period == 'daily' else 'weekly'} alert:", ""]
    for d in roles:
        where = " · ".join(x for x in (d.get("location") or "", d.get("salary") or "") if x)
        lines += [f"{d.get('title', '')} at {d.get('company', '')}" + (f" ({where})" if where else ""), f"  {d.get('url', '')}", ""]
    lines += [f"See every role, with the checks behind it: {public_url.rstrip('/')}/app#today", "",
              "You get this because job alerts are on. Turn them off in Settings > Job alerts.", "Propelo"]
    return subject, "\n".join(lines)


def send_due(db: Database, public_url: str, now: datetime | None = None, log=print) -> int:
    """Queue a digest for everyone whose alert is due and who has new roles. Returns how many were queued."""
    now = now or datetime.now(timezone.utc)
    sent = 0
    with db.tx() as c:
        users = c.all("SELECT id, email, name FROM users WHERE email_verified_at IS NOT NULL AND disabled_at IS NULL")
        for u in users:
            sdoc = repo.get_doc(c, u["id"], "settings", "profile")
            s = (sdoc or {}).get("data") or {}
            period = s.get("alerts")
            if period not in EVERY:
                continue
            last = _ts(s.get("alertsSentAt") or "") or (now - EVERY[period] - timedelta(hours=1))
            if now - last < EVERY[period]:
                continue
            fresh = []
            for j in repo.list_docs(c, u["id"], "jobs"):
                d = j["data"]
                found = _ts(d.get("foundAt") or d.get("createdAt") or "")
                if d.get("stage") in ("found", "ready", None, "") and not d.get("manual") and found and found > last and d.get("url"):
                    fresh.append(d)
            fresh.sort(key=lambda d: (-_score(d), d.get("postedAt") or ""), reverse=False)
            repo.update_doc(c, u["id"], "settings", "profile", {"alertsSentAt": now.strftime("%Y-%m-%dT%H:%M:%SZ")})
            if not fresh:
                continue
            subject, text = digest((u.get("name") or "").split(" ")[0], fresh[:MAX_ROLES], period, public_url)
            repo.enqueue(c, "send_email", {"to": u["email"], "subject": subject, "text": text}, user_id=u["id"], max_attempts=6)
            sent += 1
    log(f"job alerts: {sent} queued")
    return sent
