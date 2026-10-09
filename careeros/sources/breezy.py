"""Breezy HR public JSON: https://{company}.breezy.hr/json (no descriptions in the list)."""

from __future__ import annotations

from .. import extract
from ..models import Job
from .http import get_json

API = "https://{token}.breezy.hr/json"


def normalize(item: dict, company: str) -> Job:
    loc = item.get("location") or {}
    country = (loc.get("country") or {}).get("name", "") if isinstance(loc.get("country"), dict) else (loc.get("country") or "")
    location = loc.get("name") or ", ".join(x for x in (loc.get("city"), loc.get("state", {}).get("name") if isinstance(loc.get("state"), dict) else loc.get("state"), country) if x)
    mode = "remote" if loc.get("is_remote") else ""
    return Job(
        company=company,
        title=(item.get("name") or "").strip(),
        url=item.get("url", ""),
        source="Breezy",
        location=location,
        work_mode=extract.work_mode(structured=mode, location=location),
        posted_at=item.get("published_date", ""),
        req_id=str(item.get("friendly_id") or item.get("id") or ""),
        raw={"type": (item.get("type") or {}).get("name", "")},
    )


def fetch(token: str, company: str | None = None) -> list[Job]:
    data = get_json(API.format(token=token))
    return [normalize(j, company or token) for j in data or []]
