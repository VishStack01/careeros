"""Workday career sites: POST https://{tenant}.{wdN}.myworkdayjobs.com/wday/cxs/{tenant}/{site}/jobs

Most large employers that pay freshers well (NVIDIA, Salesforce, Adobe, PayPal,
Qualcomm, Walmart Global Tech, Visa, Intel, Cisco and others) post on Workday.
The token is "tenant/wdN/site", e.g. "nvidia/wd5/NVIDIAExternalCareerSite".

The list endpoint is narrowed to India through the site's own country facet
when it has one (else a search for "India"), and to tech titles. Only those
roles get the detail request, which carries the description and start date.
Endpoint shapes follow the ats-scrapers project (MIT, github.com/kalil0321/ats-scrapers).
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone

from .. import extract
from ..models import Job, iso
from ..textutil import html_to_text
from .http import FetchError, post_json, get_json

PAGE = 20  # Workday rejects larger pages
MAX_PAGES = 15
DETAIL_CAP = 40
TECH = re.compile(r"engineer|developer|\bsde\b|\bswe\b|machine learning|\bml\b|\bai\b|data scien|devops|\bsre\b|software|"
                  r"full[ -]?stack|back[ -]?end|front[ -]?end|mobile|android|\bios\b|graduate|intern|trainee|new grad|associate", re.I)
_URL = re.compile(r"^https?://(?P<tenant>[^./]+)\.(?P<wd>wd\d+)\.myworkdayjobs\.com/(?:[a-z]{2}-[A-Z]{2}/)?(?P<site>[^/?#]+)")


def parse_token(token: str) -> tuple[str, str, str]:
    tenant, wd, site = (token.split("/") + ["", "", ""])[:3]
    if not (tenant and re.fullmatch(r"wd\d+", wd) and site):
        raise ValueError(f"Workday token must be tenant/wdN/site, got {token!r}")
    return tenant, wd, site


def token_from_url(url: str) -> str | None:
    m = _URL.match((url or "").strip())
    return f"{m['tenant']}/{m['wd']}/{m['site']}" if m else None


def base(token: str) -> str:
    tenant, wd, site = parse_token(token)
    return f"https://{tenant}.{wd}.myworkdayjobs.com"


def api(token: str) -> str:
    tenant, wd, site = parse_token(token)
    return f"{base(token)}/wday/cxs/{tenant}/{site}"


def posted_from(text: str, now: datetime | None = None) -> str:
    """'Posted Today' / 'Posted Yesterday' / 'Posted 5 Days Ago' / 'Posted 30+ Days Ago' -> ISO date."""
    now = now or datetime.now(timezone.utc)
    t = (text or "").lower()
    if "today" in t:
        days = 0
    elif "yesterday" in t:
        days = 1
    else:
        m = re.search(r"(\d+)\+?\s*days?", t)
        if not m:
            return ""
        days = int(m.group(1))
    return iso((now - timedelta(days=days)).replace(hour=0, minute=0, second=0, microsecond=0))


def india_facet(facets: list) -> tuple[str, str] | None:
    """(facetParameter, id) of the India value in a country facet, searched recursively."""
    for f in facets or []:
        if not isinstance(f, dict):
            continue
        param = str(f.get("facetParameter") or "")
        for v in f.get("values") or []:
            if not isinstance(v, dict):
                continue
            if "facetParameter" in v:  # nested group
                hit = india_facet([v])
                if hit:
                    return hit
            elif "country" in param.lower() and str(v.get("descriptor", "")).strip().lower() == "india" and v.get("id"):
                return param, str(v["id"])
    return None


def _search(token: str, facets: dict, text: str, offset: int) -> dict:
    return post_json(api(token) + "/jobs", {"appliedFacets": facets, "limit": PAGE, "offset": offset, "searchText": text}, timeout=20)


def listings(token: str) -> list[dict]:
    first = _search(token, {}, "", 0)
    hit = india_facet(first.get("facets") or [])
    facets, text = ({hit[0]: [hit[1]]}, "") if hit else ({}, "India")
    out, offset = [], 0
    page = _search(token, facets, text, 0)
    total = int(page.get("total") or 0)
    while True:
        out += page.get("jobPostings") or []
        offset += PAGE
        if offset >= total or offset >= PAGE * MAX_PAGES or not page.get("jobPostings"):
            break
        page = _search(token, facets, text, offset)
    return out


def normalize(item: dict, token: str, company: str, detail: dict | None = None, now: datetime | None = None) -> Job:
    tenant, wd, site = parse_token(token)
    path = item.get("externalPath") or ""
    info = (detail or {}).get("jobPostingInfo") or {}
    text = html_to_text(info.get("jobDescription") or "")
    location = info.get("location") or item.get("locationsText") or ""
    extra = ", ".join(x for x in (info.get("additionalLocations") or []) if isinstance(x, str))
    if extra and extra not in location:
        location = f"{location}; {extra}"
    posted = (info.get("startDate") or "")[:10]
    posted = f"{posted}T00:00:00Z" if posted else posted_from(item.get("postedOn") or "", now)
    remote = str(item.get("remoteType") or info.get("remoteType") or "")
    return Job(
        company=company,
        title=(item.get("title") or info.get("title") or "").strip(),
        url=info.get("externalUrl") or f"{base(token)}/{site}{path}",
        source="Workday",
        location=location,
        work_mode=extract.work_mode(structured=remote, location=location, text=text),
        description=text,
        posted_at=posted,
        req_id=str((item.get("bulletFields") or [""])[0] or path.rsplit("_", 1)[-1]),
        raw={"externalPath": path},
    )


def fetch(token: str, company: str | None = None) -> list[Job]:
    jobs, details = [], 0
    for item in listings(token):
        title = item.get("title") or ""
        detail = None
        if TECH.search(title) and details < DETAIL_CAP and item.get("externalPath"):
            details += 1
            try:
                detail = get_json(api(token) + item["externalPath"], timeout=20, retries=1)
            except FetchError:
                detail = None
        jobs.append(normalize(item, token, company or parse_token(token)[0], detail))
    return jobs
