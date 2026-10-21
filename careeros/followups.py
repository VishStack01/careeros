"""When to follow up, and when to stop.

Cadence (adapted from career-ops, MIT):
* applied, no reply: a first follow-up 7 days after applying, a second 7 days
  after that, then stop. Two unanswered nudges is the limit.
* they replied (stage screen): answer within 1 day.
* an interview: a thank-you note the day after.
Once a role moves past "applied" (a reply, an interview, a rejection, an offer),
the unsent applied follow-ups are closed as not needed.

Each follow-up is {kind, label, due, note, done}. The `outreach` skill drafts the
message for each one; the user sends it.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

CADENCE = {"applied_first": 7, "applied_next": 7, "applied_max": 2, "responded": 1, "interview_thankyou": 1}
NOTE = {
    "applied": "Add something new: a relevant commit, a short teardown of their product, or a result. Never 'just checking in'.",
    "responded": "Reply to the recruiter: confirm interest, availability and anything they asked for.",
    "thankyou": "Thank the interviewers for their time and add one specific follow-up to something you discussed.",
}
PAST_APPLIED = ("screen", "interview", "offer", "rejected", "withdrawn")


def _dt(s) -> datetime | None:
    try:
        d = datetime.fromisoformat(str(s).replace("Z", "+00:00"))
        return d if d.tzinfo else d.replace(tzinfo=timezone.utc)
    except (TypeError, ValueError):
        return None


def _iso(d: datetime) -> str:
    return d.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def plan(job: dict, now: datetime | None = None) -> list[dict]:
    """The follow-ups a role should have at its current stage (before merging with what exists)."""
    now = now or datetime.now(timezone.utc)
    stage = job.get("stage")
    out = []
    applied = _dt(job.get("appliedAt"))
    if stage == "applied" and applied:
        due = applied
        for n in range(1, CADENCE["applied_max"] + 1):
            due = due + timedelta(days=CADENCE["applied_first"] if n == 1 else CADENCE["applied_next"])
            out.append({"kind": f"applied-{n}", "label": "First follow-up" if n == 1 else "Second follow-up", "due": _iso(due), "note": NOTE["applied"], "done": False})
    if stage == "screen":
        at = _dt(job.get("screenAt")) or now
        out.append({"kind": "responded", "label": "Reply to the recruiter", "due": _iso(at + timedelta(days=CADENCE["responded"])), "note": NOTE["responded"], "done": False})
    if stage == "interview":
        at = _dt(job.get("interviewAt"))
        if at:
            out.append({"kind": f"thankyou-{at.date().isoformat()}", "label": "Thank-you note", "due": _iso(at + timedelta(days=CADENCE["interview_thankyou"])),
                        "note": NOTE["thankyou"], "done": False})
    return out


def seed(job: dict, now: datetime | None = None) -> list[dict]:
    """followUps for the job: existing ones kept (done ones untouched), the stage's
    planned ones added once, applied nudges closed once the role moved on."""
    now = now or datetime.now(timezone.utc)
    cur = [dict(f) for f in job.get("followUps") or [] if isinstance(f, dict)]
    have = {f.get("kind") for f in cur if f.get("kind")}
    if job.get("stage") in PAST_APPLIED:
        for f in cur:
            if str(f.get("kind", "")).startswith("applied-") and not f.get("done"):
                f.update(done=True, skipped=True, doneAt=_iso(now), note="Not needed: the role moved on.")
    for f in plan(job, now):
        if f["kind"] not in have:
            cur.append(f)
    return cur


def due(jobs: list[dict], now: datetime | None = None) -> list[tuple[dict, dict]]:
    """(job, follow-up) pairs due by now and not done, oldest first."""
    now = now or datetime.now(timezone.utc)
    out = []
    for j in jobs:
        for f in j.get("followUps") or []:
            d = _dt(f.get("due"))
            if d and d <= now and not f.get("done"):
                out.append((j, f))
    return sorted(out, key=lambda x: x[1].get("due", ""))
