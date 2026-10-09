"""Personio public XML feed: https://{company}.jobs.personio.de/xml"""

from __future__ import annotations

import xml.etree.ElementTree as ET

from .. import extract
from ..models import Job
from ..textutil import html_to_text
from .http import get_text

API = "https://{token}.jobs.personio.de/xml"


def _t(el, tag: str) -> str:
    x = el.find(tag)
    return (x.text or "").strip() if x is not None and x.text else ""


def _years(v: str) -> str:
    """Personio buckets: 'lt-1', '1-2', '2-5', '5-7', '7+' ..."""
    v = (v or "").strip().lower()
    if v.startswith("lt-"):
        return f"0-{v[3:]} years"
    return f"{v} years" if v[:1].isdigit() else ""


def normalize(pos: ET.Element, company: str, token: str) -> Job:
    descs = []
    for d in pos.findall("./jobDescriptions/jobDescription"):
        descs.append(_t(d, "name") + ":")
        descs.append(html_to_text(_t(d, "value")))
    text = "\n".join(descs)
    location = _t(pos, "office")
    jid = _t(pos, "id")
    years = _t(pos, "yearsOfExperience")
    return Job(
        company=company,
        title=_t(pos, "name"),
        url=f"https://{token}.jobs.personio.de/job/{jid}",
        source="Personio",
        location=location,
        work_mode=extract.work_mode(location=location, text=text),
        description=text,
        posted_at=_t(pos, "createdAt"),
        req_id=jid,
        raw={"experience_header": _years(years), "seniority": _t(pos, "seniority")},
    )


def fetch(token: str, company: str | None = None) -> list[Job]:
    root = ET.fromstring(get_text(API.format(token=token)))
    return [normalize(p, company or token, token) for p in root.findall("position")]
