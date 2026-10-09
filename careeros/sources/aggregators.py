"""Remote job boards with public feeds.

These are boards that publish their listings as JSON or RSS for anyone to read,
so the scan can include them alongside company career pages. Every fetcher
returns Jobs with the board's own listing URL, so the dashboard links back to
the source (several boards ask for exactly that in their terms).

Polling limits are the boards' own requests, not ours: Remotive asks for no
more than about four calls a day, Jobicy about one an hour. `MIN_HOURS` keeps
the 3-hourly scan inside them by reusing the last result until it is due.
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

from .. import extract
from ..models import Job, iso
from ..textutil import html_to_text
from .http import FetchError, get_json, get_text


def _epoch(v) -> str:
    try:
        v = float(v)
    except (TypeError, ValueError):
        return ""
    if v > 1e12:  # milliseconds
        v /= 1000
    return iso(datetime.fromtimestamp(v, tz=timezone.utc))


def _plain_dt(s: str) -> str:
    """'2026-10-04 12:31:20' or ISO without zone -> ISO in UTC."""
    s = (s or "").strip()
    if not s:
        return ""
    try:
        dt = datetime.fromisoformat(s.replace(" ", "T", 1).replace("Z", "+00:00"))
    except ValueError:
        return s
    return iso(dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc))


def _money(lo, hi, cur: str = "USD", per: str = "year") -> str:
    try:
        lo, hi = float(lo or 0), float(hi or 0)
    except (TypeError, ValueError):
        return ""
    if not hi:
        return ""
    sym = {"USD": "$", "INR": "₹"}.get((cur or "USD").upper(), (cur or "") + " ")
    lo = lo or hi
    return f"{sym}{int(lo):,} - {sym}{int(hi):,} /{per}"


def _remote_job(company, title, url, source, where, text, posted, salary="", req="") -> Job:
    where = (where or "").strip()
    location = f"Remote - {where}" if where and not re.match(r"remote\b", where, re.I) else (where or "Remote")
    return Job(company=(company or "").strip(), title=(title or "").strip(), url=url or "", source=source,
               location=location, work_mode="remote", description=text, posted_at=posted,
               salary_text=salary, req_id=str(req or ""))


# ------------------------------------------------------------------ boards

def remoteok() -> list[Job]:
    data = get_json("https://remoteok.com/api")
    out = []
    for it in data if isinstance(data, list) else []:
        if not isinstance(it, dict) or not it.get("position"):
            continue  # the first element is the terms notice
        out.append(_remote_job(it.get("company"), it.get("position"), it.get("url"), "Remote OK",
                               it.get("location") or "", html_to_text(it.get("description", "")),
                               it.get("date") or _epoch(it.get("epoch")),
                               _money(it.get("salary_min"), it.get("salary_max")), it.get("id")))
    return out


def remotive() -> list[Job]:
    data = get_json("https://remotive.com/api/remote-jobs?limit=500")
    return [_remote_job(it.get("company_name"), it.get("title"), it.get("url"), "Remotive",
                        it.get("candidate_required_location") or "", html_to_text(it.get("description", "")),
                        _plain_dt(it.get("publication_date", "")), it.get("salary") or "", it.get("id"))
            for it in data.get("jobs", [])]


def himalayas(pages: int = 15) -> list[Job]:
    out = []
    for page in range(pages):
        data = get_json(f"https://himalayas.app/jobs/api?limit=20&offset={page * 20}")
        jobs = data.get("jobs", [])
        for it in jobs:
            restr = [r.get("name", "") if isinstance(r, dict) else str(r) for r in it.get("locationRestrictions") or []]
            out.append(_remote_job(it.get("companyName"), it.get("title"), it.get("applicationLink") or it.get("guid"),
                                   "Himalayas", ", ".join(restr) or "Worldwide",
                                   html_to_text(it.get("description") or it.get("excerpt") or ""),
                                   _epoch(it.get("pubDate")), _money(it.get("minSalary"), it.get("maxSalary"), it.get("currency") or "USD"),
                                   it.get("guid")))
        if len(jobs) < 20:
            break
    return out


def jobicy() -> list[Job]:
    data = get_json("https://jobicy.com/api/v2/remote-jobs?count=100")
    return [_remote_job(it.get("companyName"), it.get("jobTitle"), it.get("url"), "Jobicy", it.get("jobGeo") or "",
                        html_to_text(it.get("jobDescription") or it.get("jobExcerpt") or ""), _plain_dt(it.get("pubDate", "")),
                        _money(it.get("annualSalaryMin"), it.get("annualSalaryMax"), it.get("salaryCurrency") or "USD"), it.get("id"))
            for it in data.get("jobs", [])]


def workingnomads() -> list[Job]:
    data = get_json("https://www.workingnomads.com/api/exposed_jobs/")
    return [_remote_job(it.get("company_name"), it.get("title"), it.get("url"), "Working Nomads", it.get("location") or "",
                        html_to_text(it.get("description", "")), _plain_dt(it.get("pub_date", "")))
            for it in data if isinstance(it, dict)]


def weworkremotely() -> list[Job]:
    root = ET.fromstring(get_text("https://weworkremotely.com/remote-jobs.rss"))
    out = []
    for item in root.iter("item"):
        raw_title = item.findtext("title") or ""
        company, _, title = raw_title.partition(":")
        if not title:
            company, title = "", raw_title
        try:
            posted = iso(parsedate_to_datetime(item.findtext("pubDate") or ""))
        except (TypeError, ValueError):
            posted = ""
        out.append(_remote_job(company, title, item.findtext("link"), "We Work Remotely", item.findtext("region") or "",
                               html_to_text(item.findtext("description") or ""), posted))
    return out


_HIRING = re.compile(r"^(?P<company>.+?)\s*(?:\((?:YC|yc)[^)]*\))?\s+(?:is\s+)?hiring\s*(?:an?\s+)?(?P<role>.*)$", re.I)
_TITLE_LOC = re.compile(r"\s+(?:in|–|-)\s+(?P<loc>(?:remote|bangalore|bengaluru|hyderabad|chennai|india|[A-Z][\w .,/]+))\s*$", re.I)


def hn_jobs(limit: int = 120) -> list[Job]:
    """Job posts by Y Combinator companies on Hacker News."""
    ids = get_json("https://hacker-news.firebaseio.com/v0/jobstories.json")[:limit]
    out = []
    for i in ids:
        try:
            it = get_json(f"https://hacker-news.firebaseio.com/v0/item/{i}.json", min_interval=0.05)
        except FetchError:
            continue
        m = _HIRING.match(it.get("title") or "")
        if not m:
            continue
        role, loc = m.group("role"), ""
        lm = _TITLE_LOC.search(role)
        if lm:
            role, loc = role[: lm.start()], lm.group("loc")
        if re.search(r"\(remote\)|remote", it.get("title", ""), re.I):
            loc = loc or "Remote"
        text = html_to_text(it.get("text") or "")
        out.append(Job(company=m.group("company").strip(), title=role.strip(" .") or "Engineer", url=it.get("url") or f"https://news.ycombinator.com/item?id={i}",
                       source="Hacker News jobs", location=loc, work_mode=extract.work_mode(location=loc, text=text),
                       description=text, posted_at=_epoch(it.get("time")), req_id=str(i)))
    return out


_ROLE_HINT = re.compile(r"engineer|developer|scientist|ml|ai\b|data|designer|product|sre|devops|founding|intern|research", re.I)
_LOC_HINT = re.compile(r"remote|onsite|on-site|hybrid|anywhere|worldwide|india|bangalore|bengaluru|hyderabad|chennai|pune|\b[A-Z]{2,}\b,|, [A-Z]{2}\b|london|berlin|new york|san francisco|nyc|sf\b", re.I)


def hn_who_is_hiring() -> list[Job]:
    """The monthly 'Ask HN: Who is hiring?' thread. Each top-level comment is one company."""
    hits = get_json("https://hn.algolia.com/api/v1/search_by_date?tags=story,author_whoishiring&hitsPerPage=10").get("hits", [])
    thread = next((h for h in hits if "who is hiring" in (h.get("title") or "").lower()), None)
    if not thread:
        return []
    data = get_json(f"https://hn.algolia.com/api/v1/items/{thread['objectID']}", timeout=60)
    out = []
    for c in data.get("children", []):
        html = c.get("text") or ""
        if not html:
            continue
        first = html_to_text(re.split(r"<p>", html, maxsplit=1)[0])
        parts = [p.strip() for p in first.split("|") if p.strip()]
        if len(parts) < 2:
            continue
        text = html_to_text(html)
        role = next((p for p in parts[1:] if _ROLE_HINT.search(p) and len(p) < 120), "")
        loc = "; ".join(p for p in parts[1:] if _LOC_HINT.search(p) and p != role)[:160]
        if not role:
            continue
        out.append(Job(company=re.sub(r"\s*\(.*?\)$", "", parts[0])[:80], title=role[:120],
                       url=f"https://news.ycombinator.com/item?id={c.get('id')}", source="HN Who is hiring",
                       location=loc, work_mode=extract.work_mode(location=loc, text=text), description=text,
                       posted_at=_plain_dt(c.get("created_at", "")), req_id=str(c.get("id", ""))))
    return out


def arbeitnow(pages: int = 3) -> list[Job]:
    out = []
    for page in range(1, pages + 1):
        data = get_json(f"https://www.arbeitnow.com/api/job-board-api?page={page}")
        for it in data.get("data", []):
            if not it.get("remote"):
                continue
            out.append(_remote_job(it.get("company_name"), it.get("title"), it.get("url"), "Arbeitnow", it.get("location") or "",
                                   html_to_text(it.get("description", "")), _epoch(it.get("created_at")), "", it.get("slug")))
        if not (data.get("links") or {}).get("next"):
            break
    return out


AGGREGATORS = {
    "remoteok": remoteok,
    "remotive": remotive,
    "himalayas": himalayas,
    "jobicy": jobicy,
    "workingnomads": workingnomads,
    "weworkremotely": weworkremotely,
    "hn-jobs": hn_jobs,
    "hn-who-is-hiring": hn_who_is_hiring,
    "arbeitnow": arbeitnow,
}

MIN_HOURS = {"remotive": 6, "jobicy": 1, "hn-who-is-hiring": 12, "arbeitnow": 6}
