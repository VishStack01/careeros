"""The gatekeeper: run every filter on a role and keep the reasons.

Each gate returns a Check with the deciding sentence from the posting. A role
is kept only if every gate passes. Skipped roles keep their checks too, so the
skip log can say exactly why, and you can overrule it.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime, timezone

from . import extract, geo
from .models import Check, Job, iso
from .settings import Settings


@dataclass
class Decision:
    kept: bool
    checks: list[Check]
    region: str
    priority: bool


def _parse_dt(s: str) -> datetime | None:
    if not s:
        return None
    try:
        dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _facts(job: Job) -> dict | None:
    """Pre-extracted facts (from the India feed), if this job carries them."""
    f = job.raw.get("facts") if isinstance(job.raw, dict) else None
    return f if isinstance(f, dict) else None


def _kw_regex(words: list[str]) -> re.Pattern:
    parts = [r"(?<![a-z0-9])" + re.escape(w.lower()) + r"(?![a-z0-9])" for w in words if w.strip()]
    return re.compile("|".join(parts) or r"(?!x)x", re.I)


def gate_company(job: Job, s: Settings) -> Check:
    blocked = [c for c in s.company_blocklist if c.lower() in job.company.lower()]
    if blocked:
        return Check("Company", False, f"{job.company} is on your never-apply list.")
    return Check("Company", True, job.company)


def gate_role(job: Job, s: Settings) -> Check:
    title = job.title or ""
    if s.title_exclude and _kw_regex(s.title_exclude).search(title):
        return Check("Role", False, "The title matches one of your excluded words.", title)
    if not _kw_regex(s.role_keywords).search(title):
        return Check("Role", False, "The title isn't one of your target roles.", title)
    if not s.allow_internships and re.search(r"\bintern(ship)?\b", title, re.I):
        return Check("Role", False, "It's an internship, and internships are switched off.", title)
    return Check("Role", True, "Target role", title)


def gate_seniority(job: Job, s: Settings) -> Check:
    level = extract.title_seniority(job.title)
    if level == "senior" and s.max_required_years < 3:
        return Check("Seniority", False, "The title is a senior-level role.", job.title)
    return Check("Seniority", True, level or "Not stated in title", job.title)


def gate_experience(job: Job, s: Settings) -> Check:
    f = _facts(job)
    if f is not None:
        req = extract.ExperienceReq(f.get("expMin"), f.get("fresherOk"), f.get("expQuote") or "")
    else:
        req = extract.extract_experience(job.description, header=str(job.raw.get("experience_header", "")))
    if req.min_years is not None and req.min_years > s.max_required_years:
        return Check(
            "Experience", False,
            f"Asks for {req.describe()}; your limit is {s.max_required_years:g} year(s).", req.quote,
        )
    if req.min_years is None and req.fresher_ok is False and s.max_required_years < 1:
        return Check("Experience", False, "The posting says it isn't open to freshers.", req.quote)
    return Check("Experience", True, req.describe(), req.quote)


def gate_freshness(job: Job, s: Settings, now: datetime) -> tuple[Check, bool]:
    posted = _parse_dt(job.posted_at)
    if not posted:
        return Check("Posted", True, "Posting date not shown"), False
    days = (now - posted).total_seconds() / 86400
    hours = days * 24
    label = f"{int(hours)}h ago" if hours < 48 else f"{int(days)} days ago"
    if days > s.ghost_after_days:
        return Check("Posted", False, f"Open for {int(days)} days, which usually means a stale or evergreen listing."), False
    if days > s.max_posting_age_days:
        return Check("Posted", False, f"Posted {label}; your window is {s.max_posting_age_days} days."), False
    return Check("Posted", True, f"Posted {label}"), hours <= s.priority_within_hours


def gate_open(job: Job, today: date) -> Check:
    f = _facts(job)
    q = (f.get("closedQuote") or "") if f is not None else extract.closed_signal(job.description)
    if q:
        return Check("Open", False, "The posting says it's closed.", q)
    if job.apply_by:
        try:
            deadline = date.fromisoformat(job.apply_by)
        except ValueError:
            deadline = None
        if deadline and deadline < today:
            return Check("Open", False, f"Applications closed on {deadline.isoformat()}.")
    return Check("Open", True, f"Open{', apply by ' + job.apply_by if job.apply_by else ''}")


def gate_location(job: Job, s: Settings) -> tuple[Check, str]:
    p = s.location
    mode = job.work_mode
    where = geo.classify(job.location)
    if mode == "remote":
        f = _facts(job)
        if f is not None and "scope" in f:
            scope = extract.RemoteScope(f.get("scopeEligible"), f.get("scope") or "", f.get("scopeQuote") or "")
        else:
            scope = extract.remote_scope(job.location, job.description)
        if scope.scope == "worldwide":
            return Check("Location", True, "Remote worldwide", scope.quote), "remote-global"
        if where["india"] or scope.scope == "india":
            if p.rest_of_india == "never" and not where["south"]:
                return Check("Location", False, "Remote roles in India are switched off."), ""
            return Check("Location", True, "Remote, India", scope.quote or job.location), "remote-india"
        if scope.india_eligible is True:
            return Check("Location", True, f"Remote ({scope.scope}), open to India", scope.quote), "remote-global"
        if scope.india_eligible is False:
            who = {"us": "people in the US", "europe": "people in Europe", "americas": "people in the Americas", "timezone": "a time-zone range that excludes India"}.get(scope.scope, scope.scope)
            return Check("Location", False, f"Remote, but only for {who}.", scope.quote), ""
        if p.abroad == "never":
            return Check("Location", False, "Remote abroad is switched off."), ""
        if p.keep_unclear_remote:
            return Check("Location", True, "Remote; the posting doesn't say who can apply. Check before applying.", job.location), "remote-global"
        return Check("Location", False, "Remote, but the posting doesn't say people in India can apply.", job.location), ""

    mode_txt = {"hybrid": "Hybrid", "onsite": "On-site"}.get(mode, "Work mode not stated")
    if where["south"]:
        if p.south_india == "any" or (p.south_india == "remote" and mode == "remote"):
            return Check("Location", True, f"{mode_txt}, {where['south'].title()} (south India)", job.location), "south-india"
        return Check("Location", False, f"{mode_txt} in south India, and you only want remote there.", job.location), ""
    if where["india"]:
        if p.rest_of_india == "any":
            return Check("Location", True, f"{mode_txt}, {job.location}", job.location), "south-india"
        return Check("Location", False, f"{mode_txt} in {job.location}. Outside south India you only want remote roles.", job.location), ""
    if where["abroad"]:
        return Check("Location", False, f"{mode_txt} abroad ({job.location}).", job.location), ""
    return Check("Location", True, "Location not stated. Check before applying.", job.location), "south-india"


def gate_pay(job: Job, s: Settings) -> tuple[Check, extract.Salary | None]:
    f = _facts(job)
    sal = extract.parse_salary(job.salary_text, s.usd_inr)
    if not sal and f is not None and f.get("salaryHigh") is not None:
        sal = extract.Salary(f.get("salaryLow") or f["salaryHigh"], f["salaryHigh"], "", "year", f.get("salaryQuote") or "")
    if not sal and f is None:
        sal = extract.parse_salary(job.description, s.usd_inr)
    if not sal:
        return Check("Pay", True, "Not stated"), None
    if s.salary_floor_lpa is not None and sal.high_lpa < s.salary_floor_lpa:
        return Check("Pay", False, f"Pays {sal.describe()}, below your {s.salary_floor_lpa:g} LPA floor.", sal.quote), sal
    return Check("Pay", True, sal.describe(), sal.quote), sal


def gate_dealbreakers(job: Job, s: Settings) -> Check:
    for word in s.dealbreakers:
        m = re.search(re.escape(word), job.description or "", re.I)
        if m:
            from .textutil import quote_around
            return Check("Dealbreaker", False, f"Mentions '{word}'.", quote_around(job.description, *m.span()))
    return Check("Dealbreaker", True, "None found")


def evaluate(job: Job, s: Settings, now: datetime | None = None) -> Decision:
    now = now or datetime.now(timezone.utc)
    checks: list[Check] = [gate_company(job, s), gate_role(job, s), gate_seniority(job, s), gate_experience(job, s)]
    fresh, priority = gate_freshness(job, s, now)
    checks += [fresh, gate_open(job, now.date())]
    loc, region = gate_location(job, s)
    pay, sal = gate_pay(job, s)
    checks += [loc, pay, gate_dealbreakers(job, s)]
    if sal and not job.salary_text:
        job.salary_text = sal.describe()
    kept = all(c.passed for c in checks)
    return Decision(kept, checks, region if kept else "", priority if kept else False)


def apply_decision(job: Job, s: Settings, now: datetime | None = None) -> Decision:
    d = evaluate(job, s, now)
    job.checks = d.checks
    job.region = d.region
    job.priority = d.priority
    job.stage = "found" if d.kept else "skipped"
    job.found_at = job.found_at or iso(now or datetime.now(timezone.utc))
    return d
