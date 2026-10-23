"""Amazon jobs in India: GET https://www.amazon.jobs/en/search.json

Public JSON that honours the site's own filters; we ask for India
(normalized_country_code[]=IND) and the software, ML and data categories.
Field names follow the ats-scrapers project (MIT, github.com/kalil0321/ats-scrapers).
Token: the country code, "IND".
"""

from __future__ import annotations

from datetime import datetime
from urllib.parse import urlencode

from .. import extract
from ..models import Job
from ..textutil import html_to_text
from .http import get_json

SEARCH = "https://www.amazon.jobs/en/search.json"
CATEGORIES = ["software-development", "machine-learning-science", "data-science", "solutions-architect"]
PAGE, MAX = 100, 600


def _date(s: str) -> str:
    for fmt in ("%B %d, %Y", "%Y-%m-%d"):
        try:
            return datetime.strptime((s or "").strip(), fmt).strftime("%Y-%m-%dT00:00:00Z")
        except ValueError:
            continue
    return ""


def normalize(item: dict, company: str = "Amazon") -> Job:
    path = item.get("job_path") or item.get("url_next_step") or ""
    url = path if path.startswith("http") else f"https://www.amazon.jobs{path}" if path else f"https://www.amazon.jobs/en/jobs/{item.get('id_icims', '')}"
    parts = [item.get("description") or item.get("description_short") or ""]
    for key, label in (("basic_qualifications", "Basic qualifications"), ("preferred_qualifications", "Preferred qualifications")):
        if item.get(key):
            parts.append(f"{label}:\n{item[key]}")
    text = html_to_text("\n\n".join(p for p in parts if p))
    location = item.get("normalized_location") or item.get("location") or ""
    return Job(
        company=company,
        title=(item.get("title") or "").strip(),
        url=url,
        source="Amazon jobs",
        location=location,
        work_mode=extract.work_mode(location=location, text=text),
        description=text,
        posted_at=_date(item.get("posted_date") or ""),
        req_id=str(item.get("id_icims") or item.get("id") or ""),
    )


def fetch(token: str = "IND", company: str | None = None) -> list[Job]:
    jobs: list[Job] = []
    seen: set[str] = set()
    for cat in CATEGORIES:
        offset = 0
        while offset < MAX:
            q = urlencode([("result_limit", PAGE), ("offset", offset), ("sort", "recent"),
                           ("normalized_country_code[]", token or "IND"), ("category[]", cat)])
            hits = (get_json(f"{SEARCH}?{q}", timeout=25) or {}).get("jobs") or []
            for h in hits:
                j = normalize(h, company or "Amazon")
                if j.url not in seen:
                    seen.add(j.url)
                    jobs.append(j)
            if len(hits) < PAGE:
                break
            offset += PAGE
    return jobs
