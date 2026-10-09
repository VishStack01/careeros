"""Greenhouse job board API: https://boards-api.greenhouse.io/v1/boards/{token}/jobs?content=true"""

from __future__ import annotations

from .. import extract
from ..models import Job
from ..textutil import html_to_text
from .http import get_json

API = "https://boards-api.greenhouse.io/v1/boards/{token}/jobs?content=true"


def normalize(item: dict, company: str) -> Job:
    text = html_to_text(item.get("content", ""))
    location = (item.get("location") or {}).get("name", "")
    offices = ", ".join(o.get("name", "") for o in item.get("offices", []) if o.get("name"))
    if offices and offices not in location:
        location = f"{location}; {offices}" if location else offices
    posted = item.get("first_published") or item.get("updated_at") or ""
    return Job(
        company=company,
        title=item.get("title", "").strip(),
        url=item.get("absolute_url", ""),
        source="Greenhouse",
        location=location,
        work_mode=extract.work_mode(location=location, text=text),
        description=text,
        posted_at=posted,
        req_id=str(item.get("requisition_id") or item.get("id") or ""),
        raw={"id": item.get("id")},
    )


def fetch(token: str, company: str | None = None) -> list[Job]:
    data = get_json(API.format(token=token))
    return [normalize(j, company or token) for j in data.get("jobs", [])]
