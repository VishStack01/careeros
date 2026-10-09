"""SmartRecruiters public postings API: https://api.smartrecruiters.com/v1/companies/{id}/postings

The list endpoint has no description; `describe()` fetches one posting's text.
The scan only calls it for postings that already passed the location and role pre-filter.
"""

from __future__ import annotations

from .. import extract
from ..models import Job
from ..textutil import html_to_text
from .http import get_json

LIST = "https://api.smartrecruiters.com/v1/companies/{token}/postings?limit=100&offset={offset}"
DETAIL = "https://api.smartrecruiters.com/v1/companies/{token}/postings/{id}"


def normalize(item: dict, company: str, token: str) -> Job:
    loc = item.get("location") or {}
    location = loc.get("fullLocation") or ", ".join(x for x in (loc.get("city"), loc.get("region"), (loc.get("country") or "").upper()) if x)
    level = (item.get("experienceLevel") or {}).get("label", "")
    mode = "remote" if loc.get("remote") else ("hybrid" if loc.get("hybrid") else "")
    return Job(
        company=company,
        title=(item.get("name") or "").strip(),
        url=f"https://jobs.smartrecruiters.com/{token}/{item.get('id')}",
        source="SmartRecruiters",
        location=location,
        work_mode=extract.work_mode(structured=mode, location=location),
        posted_at=item.get("releasedDate", ""),
        req_id=str(item.get("refNumber") or item.get("id") or ""),
        raw={"experience_header": level if level.lower() in ("entry level", "internship", "associate") else "",
             "level": level, "detail_url": DETAIL.format(token=token, id=item.get("id")), "needs_detail": True},
    )


def describe(job: Job) -> Job:
    """Fill in the description from the posting detail endpoint."""
    url = job.raw.get("detail_url")
    if not url:
        return job
    data = get_json(url)
    sections = ((data.get("jobAd") or {}).get("sections") or {})
    parts = [html_to_text((sections.get(k) or {}).get("text", "")) for k in ("jobDescription", "qualifications", "additionalInformation")]
    job.description = "\n".join(p for p in parts if p)
    job.work_mode = extract.work_mode(structured=job.work_mode, location=job.location, text=job.description)
    job.raw["needs_detail"] = False
    return job


def fetch(token: str, company: str | None = None, limit: int = 1000) -> list[Job]:
    out, offset = [], 0
    while offset < limit:
        data = get_json(LIST.format(token=token, offset=offset))
        content = data.get("content", [])
        name = company or ((content[0].get("company") or {}).get("name") if content else token)
        out += [normalize(j, name, token) for j in content]
        offset += len(content)
        if not content or offset >= int(data.get("totalFound", 0)):
            break
    return out
