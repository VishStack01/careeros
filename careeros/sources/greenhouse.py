"""Greenhouse job board API: https://boards-api.greenhouse.io/v1/boards/{token}/jobs?content=true"""

from __future__ import annotations

from .. import extract
from ..models import Job
from ..textutil import html_to_text
from .http import get_json

API = "https://boards-api.greenhouse.io/v1/boards/{token}/jobs?content=true"
# Pay ranges live only on the single-job endpoint, behind pay_transparency=true.
PAY_API = "https://boards-api.greenhouse.io/v1/boards/{token}/jobs/{job_id}?pay_transparency=true"
_SYM = {"INR": "₹", "USD": "$"}


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


def pay_text(ranges: list[dict], india: bool) -> str:
    """A salary line from Greenhouse pay_input_ranges, or "" when none applies.

    Rupee ranges always apply. Dollar ranges usually describe US hiring, so they
    are used only for roles that aren't based in India (remote roles). Other
    currencies are left out rather than converted at a guessed rate."""
    best = None
    for r in ranges or []:
        cur = str(r.get("currency_type") or "").upper()
        lo, hi = r.get("min_cents"), r.get("max_cents")
        if cur not in _SYM or not isinstance(hi, (int, float)) or hi <= 0:
            continue
        if cur == "USD" and india:
            continue
        lo = lo if isinstance(lo, (int, float)) and lo > 0 else hi
        rank = (cur == "INR", "india" in str(r.get("title") or "").lower(), hi)
        if best is None or rank > best[0]:
            best = (rank, cur, int(lo) // 100, int(hi) // 100)
    if not best:
        return ""
    _, cur, lo, hi = best
    sym = _SYM[cur]
    return f"{sym}{lo:,} - {sym}{hi:,} /year"


def pay(token: str, job_id: str | int, india: bool) -> str:
    """The posted pay range for one job ("" when the company publishes none)."""
    data = get_json(PAY_API.format(token=token, job_id=job_id), timeout=15, retries=1, min_interval=0.5)
    return pay_text(data.get("pay_input_ranges") or [], india)
