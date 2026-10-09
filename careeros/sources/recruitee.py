"""Recruitee public offers API: https://{company}.recruitee.com/api/offers/"""

from __future__ import annotations

import re

from .. import extract
from ..models import Job
from ..textutil import html_to_text
from .http import get_json

API = "https://{token}.recruitee.com/api/offers/"


def _iso(s: str) -> str:
    """Recruitee dates look like '2026-10-04 10:00:00 UTC'."""
    s = (s or "").strip()
    m = re.match(r"(\d{4}-\d{2}-\d{2})[ T](\d{2}:\d{2}:\d{2})(?:\s*UTC|Z)?$", s)
    return f"{m.group(1)}T{m.group(2)}+00:00" if m else s


def normalize(item: dict, company: str) -> Job:
    location = item.get("location") or ", ".join(x for x in (item.get("city"), item.get("country")) if x)
    text = html_to_text((item.get("description") or "") + "\n" + (item.get("requirements") or ""))
    mode = "remote" if item.get("remote") else ("hybrid" if item.get("hybrid") else "")
    sal = item.get("salary") or {}
    salary = ""
    if sal.get("min") and sal.get("max"):
        cur = {"USD": "$", "INR": "₹"}.get(sal.get("currency", ""), "")
        per = {"month": "/month", "year": "/year", "hour": "/hour"}.get(sal.get("period", ""), "/year")
        salary = f"{cur}{sal['min']} - {cur}{sal['max']} {per}"
    return Job(
        company=company,
        title=(item.get("title") or "").strip(),
        url=item.get("careers_url") or item.get("url", ""),
        source="Recruitee",
        location=location,
        work_mode=extract.work_mode(structured=mode, location=location, text=text),
        description=text,
        posted_at=_iso(item.get("published_at") or item.get("created_at") or ""),
        salary_text=salary,
        req_id=str(item.get("id", "")),
    )


def fetch(token: str, company: str | None = None) -> list[Job]:
    data = get_json(API.format(token=token))
    return [normalize(j, company or token) for j in data.get("offers", []) if j.get("status", "published") == "published"]
