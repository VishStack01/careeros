"""Lever postings API: https://api.lever.co/v0/postings/{company}?mode=json"""

from __future__ import annotations

from datetime import datetime, timezone

from .. import extract
from ..models import Job, iso
from ..textutil import html_to_text
from .http import get_json

API = "https://api.lever.co/v0/postings/{company}?mode=json"


def normalize(item: dict, company: str) -> Job:
    cats = item.get("categories") or {}
    location = cats.get("location") or ", ".join(cats.get("allLocations") or [])
    parts = [item.get("descriptionPlain") or html_to_text(item.get("description", ""))]
    for block in item.get("lists") or []:
        parts.append(block.get("text", "") + ":")
        parts.append(html_to_text(block.get("content", "")))
    parts.append(item.get("additionalPlain") or html_to_text(item.get("additional", "")))
    text = "\n".join(p for p in parts if p)
    created = item.get("createdAt")
    posted = iso(datetime.fromtimestamp(created / 1000, tz=timezone.utc)) if created else ""
    salary = ""
    rng = item.get("salaryRange") or {}
    if rng.get("min") and rng.get("max"):
        sym = "$" if rng.get("currency", "USD") == "USD" else "₹" if rng.get("currency") == "INR" else ""
        per = {"per-year-salary": "/year", "per-month-salary": "/month", "per-hour-wage": "/hour"}.get(rng.get("interval", ""), "/year")
        salary = f"{sym}{rng['min']:,} - {sym}{rng['max']:,} {per}"
    return Job(
        company=company,
        title=(item.get("text") or "").strip(),
        url=item.get("hostedUrl", ""),
        source="Lever",
        location=location,
        work_mode=extract.work_mode(structured=item.get("workplaceType", ""), location=location, text=text),
        description=text,
        posted_at=posted,
        salary_text=salary,
        req_id=str(item.get("id", "")),
        raw={"commitment": cats.get("commitment", "")},
    )


def fetch(company: str, name: str | None = None) -> list[Job]:
    data = get_json(API.format(company=company))
    return [normalize(j, name or company) for j in data or []]
