"""Workable public widget API: https://apply.workable.com/api/v1/widget/accounts/{account}?details=true"""

from __future__ import annotations

from .. import extract
from ..models import Job
from ..textutil import html_to_text
from .http import get_json

API = "https://apply.workable.com/api/v1/widget/accounts/{token}?details=true"


def _location(item: dict) -> str:
    locs = item.get("locations") or [{"city": item.get("city"), "region": item.get("state"), "country": item.get("country")}]
    parts = []
    for l in locs:
        if l.get("hidden"):
            continue
        s = ", ".join(x for x in (l.get("city"), l.get("region"), l.get("country")) if x)
        if s and s not in parts:
            parts.append(s)
    return "; ".join(parts)


def normalize(item: dict, company: str) -> Job:
    location = _location(item)
    text = html_to_text(item.get("description", "") + "\n" + item.get("requirements", ""))
    remote = "remote" if item.get("telecommuting") else ""
    return Job(
        company=company,
        title=(item.get("title") or "").strip(),
        url=item.get("url") or item.get("shortlink") or item.get("application_url", ""),
        source="Workable",
        location=location,
        work_mode=extract.work_mode(structured=remote, location=location, text=text),
        description=text,
        posted_at=item.get("published_on") or item.get("created_at") or "",
        req_id=str(item.get("shortcode") or item.get("code") or ""),
        raw={"experience_header": item.get("experience") or ""},
    )


def fetch(token: str, company: str | None = None) -> list[Job]:
    data = get_json(API.format(token=token))
    return [normalize(j, company or data.get("name") or token) for j in data.get("jobs", [])]
