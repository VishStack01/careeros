"""Deduplication: one role, one record, no matter how many boards repost it."""

from __future__ import annotations

import hashlib
import re
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

from .textutil import norm, slug

_TRACKING = re.compile(r"^(utm_.*|gh_src|gh_jid|source|ref|referrer|lever-source.*|lever-origin|src|trk|refId|trackingId)$", re.I)
_COMPANY_NOISE = re.compile(
    r"\b(private|pvt|limited|ltd|llp|inc|incorporated|corp|corporation|co|company|technologies|technology|labs?|"
    r"solutions|software|systems|ai|india|the)\b"
)


def canonical_url(url: str) -> str:
    if not url:
        return ""
    p = urlparse(url.strip())
    query = [(k, v) for k, v in parse_qsl(p.query, keep_blank_values=True) if not _TRACKING.match(k)]
    path = p.path.rstrip("/") or "/"
    return urlunparse((p.scheme.lower() or "https", p.netloc.lower(), path, "", urlencode(query), ""))


def company_key(company: str) -> str:
    k = _COMPANY_NOISE.sub(" ", norm(company))
    return re.sub(r"\s+", " ", k).strip() or norm(company)


def fingerprint(company: str, title: str) -> str:
    t = re.sub(r"\([^)]*\)", " ", title or "")  # drop "(Remote)", "(Fresher)" suffixes
    key = company_key(company) + "|" + norm(t)
    return hashlib.sha1(key.encode()).hexdigest()[:16]


def job_id(company: str, title: str) -> str:
    return slug(f"{company} {title}", 80)
