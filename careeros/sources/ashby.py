"""Ashby posting API: https://api.ashbyhq.com/posting-api/job-board/{org}?includeCompensation=true"""

from __future__ import annotations

from .. import extract
from ..models import Job
from ..textutil import html_to_text
from .http import get_json

API = "https://api.ashbyhq.com/posting-api/job-board/{org}?includeCompensation=true"


def normalize(item: dict, company: str) -> Job:
    text = item.get("descriptionPlain") or html_to_text(item.get("descriptionHtml", ""))
    locs = [item.get("location", "")] + [s.get("location", "") for s in item.get("secondaryLocations") or []]
    location = ", ".join(l for l in locs if l)
    structured = item.get("workplaceType") or ("Remote" if item.get("isRemote") else "")
    comp = item.get("compensation") or {}
    salary = comp.get("compensationTierSummary") or comp.get("scrapeableCompensationSalarySummary") or ""
    return Job(
        company=company,
        title=(item.get("title") or "").strip(),
        url=item.get("jobUrl") or item.get("applyUrl", ""),
        source="Ashby",
        location=location,
        work_mode=extract.work_mode(structured=structured, location=location, text=text),
        description=text,
        posted_at=item.get("publishedAt", ""),
        salary_text=salary,
        req_id=str(item.get("id", "")),
        raw={"employmentType": item.get("employmentType", "")},
    )


def fetch(org: str, company: str | None = None) -> list[Job]:
    data = get_json(API.format(org=org))
    return [normalize(j, company or org) for j in data.get("jobs", []) if j.get("isListed", True)]
