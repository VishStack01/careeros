"""Y Combinator startup jobs (ycombinator.com/jobs), from the public listing pages.

YC's pages carry their data as JSON inside the HTML (an Inertia `data-page`
attribute). Rather than depend on exact field names, the reader walks that JSON
and treats any object with a title and job-like fields as a posting, so a
renamed field degrades one value instead of the whole source. Listings show
the salary band and minimum experience, which is why YC roles so often clear
a stated-pay rule.

YC companies that keep a Greenhouse, Lever or Ashby board are also found by
`careeros yc-companies` + `discover`, so the scan reads their full postings.
"""

from __future__ import annotations

import html as htmllib
import json
import re
from datetime import datetime, timedelta, timezone
from typing import Callable, Iterator

from .. import extract
from ..models import Job, iso
from .http import get_text

BASE = "https://www.ycombinator.com"
PAGES = [f"{BASE}/jobs/role/software-engineer/{loc}" for loc in ("india", "bengaluru", "hyderabad", "chennai", "remote")] + \
        [f"{BASE}/jobs/location/india", f"{BASE}/jobs/location/remote"]
COMPANIES = "https://raw.githubusercontent.com/yc-oss/api/main/companies/hiring.json"

_ATTR = re.compile(r'data-page="([^"]+)"')
_NEXT = re.compile(r'<script[^>]+id="__NEXT_DATA__"[^>]*>(.*?)</script>', re.S)
_JOBBY = ("salaryRange", "prettySalaryRange", "salary", "minExperience", "prettyMinExperience", "jobType", "type",
          "location", "locations", "prettyLocation", "showPath", "applyUrl")


def blobs(page: str) -> list:
    out = []
    for raw in _ATTR.findall(page) + _NEXT.findall(page):
        try:
            out.append(json.loads(htmllib.unescape(raw)))
        except ValueError:
            continue
    return out


def _walk(o) -> Iterator[dict]:
    if isinstance(o, dict):
        yield o
        for v in o.values():
            yield from _walk(v)
    elif isinstance(o, list):
        for v in o:
            yield from _walk(v)


def _first(d: dict, *keys) -> str:
    for k in keys:
        v = d.get(k)
        if isinstance(v, str) and v.strip():
            return v.strip()
        if isinstance(v, list) and v and all(isinstance(x, str) for x in v):
            return "; ".join(v)
    return ""


def _when(v: str, now: datetime) -> str:
    if not v:
        return ""
    try:
        dt = datetime.fromisoformat(v.replace("Z", "+00:00"))
        return iso(dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc))
    except ValueError:
        pass
    m = re.search(r"(\d+|an?|about an?)\s+(minute|hour|day|week|month)s?\s+ago", v, re.I)
    if not m:
        return ""
    n = 1 if not m.group(1)[0].isdigit() else int(m.group(1))
    unit = {"minute": timedelta(minutes=1), "hour": timedelta(hours=1), "day": timedelta(days=1),
            "week": timedelta(weeks=1), "month": timedelta(days=30)}[m.group(2).lower()]
    return iso(now - n * unit)


def parse(page: str, now: datetime | None = None) -> list[Job]:
    now = now or datetime.now(timezone.utc)
    jobs, seen = [], set()
    for blob in blobs(page):
        for d in _walk(blob):
            title = d.get("title")
            if not isinstance(title, str) or not title.strip() or sum(k in d for k in _JOBBY) < 2:
                continue
            path = _first(d, "url", "showPath", "jobUrl", "applyUrl")
            url = BASE + path if path.startswith("/") else path
            co = d.get("company")
            company = _first(d, "companyName") or (_first(co, "name") if isinstance(co, dict) else "")
            if not company:
                m = re.search(r"/companies/([^/]+)/jobs", url)
                company = m.group(1).replace("-", " ").title() if m else ""
            if not url or not company or url in seen:
                continue
            seen.add(url)
            loc = _first(d, "location", "prettyLocation", "locations")
            salary = _first(d, "salaryRange", "prettySalaryRange", "salary")
            exp = _first(d, "minExperience", "prettyMinExperience", "experience")
            about = _first(d, "description", "companyOneLiner", "oneLiner")
            remote = "remote" if re.search(r"\bremote\b", loc, re.I) else ""
            jobs.append(Job(company=company, title=title.strip(), url=url, source="YC jobs", location=loc,
                            work_mode=extract.work_mode(structured=remote, location=loc, text=about),
                            description=about, posted_at=_when(_first(d, "createdAt", "lastActive", "updatedAt", "postedAt"), now),
                            salary_text=salary, req_id=str(d.get("id") or ""),
                            raw={"experience_header": exp, "batch": _first(d, "companyBatchName", "batch")}))
    return jobs


def fetch(pages: list[str] = PAGES, get: Callable[[str], str] | None = None) -> list[Job]:
    get = get or (lambda u: get_text(u, timeout=30, retries=1, min_interval=1.0))
    out, seen, errors = [], set(), 0
    for u in pages:
        try:
            for j in parse(get(u)):
                if j.url not in seen:
                    seen.add(j.url)
                    out.append(j)
        except Exception:
            errors += 1
    if errors == len(pages):
        raise RuntimeError("no YC jobs page could be read")
    return out


def hiring_companies(data: list[dict]) -> list[dict]:
    """Company-list rows (for discover) for YC companies that are hiring in India or remotely."""
    rows = []
    for c in data:
        regions = " ".join(c.get("regions") or []) + " " + str(c.get("all_locations") or "")
        if not c.get("isHiring") or not re.search(r"india|remote", regions, re.I):
            continue
        slug = str(c.get("slug") or "").strip().lower()
        name = str(c.get("name") or "").strip()
        if not slug or not name:
            continue
        compact = re.sub(r"[^a-z0-9]", "", slug)
        rows.append({"name": name, "category": "deep", "city": "", "website": c.get("website") or "",
                     "slugs": " ".join(dict.fromkeys([slug, compact])), "ats": "", "token": "",
                     "source": f"yc-hiring:{c.get('batch', '')}"})
    return rows
