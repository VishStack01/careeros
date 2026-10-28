"""Deduplication: one role, one record, no matter how many boards repost it."""

from __future__ import annotations

import hashlib
import re
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

from .textutil import norm, slug

_TRACKING = re.compile(r"^(utm_.*|gh_src|gh_jid|source|ref|referrer|lever-source.*|lever-origin|src|trk|refId|trackingId)$", re.I)
_COMPANY_NOISE = re.compile(
    r"\b(private|pvt|limited|ltd|llp|inc|incorporated|corp|corporation|co|company|technologies|technology|labs?|"
    r"solutions|software|systems|ai|india|the|operations|group|holdings|gmbh|ag|plc|llc|bv)\b"
)
# Words a title's trailing "- Worldwide", ", Galway, Ireland" or "| Remote" segment is made of: a place or a work mode.
PLACE = set("remote worldwide global anywhere hybrid onsite on site office in fully 100 work from home wfh multiple cities locations "
            "based only india bengaluru bangalore hyderabad chennai pune mumbai delhi new ncr gurugram gurgaon noida kolkata kochi "
            "ahmedabad jaipur coimbatore usa us united states uk kingdom kindom ireland germany france spain italy netherlands poland "
            "portugal czech republic czechia slovakia canada mexico brazil singapore australia japan uae dubai london berlin paris "
            "amsterdam dublin galway prague kosice košice bakersfield ca ny sf san francisco york seattle austin boston toronto sydney "
            "emea apac latam eu europe asia americas north america".split())
ABBR = [(r"\bsde\b", "software development engineer"), (r"\bswe\b", "software engineer"), (r"\bsre\b", "site reliability engineer"),
        (r"\bfde\b", "forward deployed engineer"), (r"\bml\b", "machine learning"), (r"\bjr\b", "junior"), (r"\bsr\b", "senior")]
ROMAN = {"i": "1", "ii": "2", "iii": "3", "iv": "4"}
TERMS = set("fresher freshers contract contractual full part time permanent temporary internship intern new grad graduate entry level".split())


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


def title_key(title: str) -> str:
    """The role a title names, without where or how it's worked: "SDE I FTC" and "Software Development Engineer I FTC"
    match, and so do "Mobile Engineer - React Native (100% Remote) - Worldwide" and "Mobile Engineer - React Native"."""
    t = re.sub(r"\b[mfwdx]/[mfwdx]/[mfwdx]\b|\ball genders?\b", " ", (title or "").lower())
    # "(Remote)", "(100% Remote)", "(Fresher)" say where or how; "(Customer Experience)" names a different role.
    t = re.sub(r"\(([^)]*)\)|\[([^\]]*)\]", lambda m: " " if all(w in PLACE or w in TERMS for w in re.findall(r"[a-z0-9š]+", m.group(0))) else " " + m.group(0)[1:-1] + " ", t)
    parts = re.split(r"\s+[-–—|]\s+|,\s+|\s+/\s+", t)
    while len(parts) > 1 and all(w in PLACE for w in re.findall(r"[a-z0-9š]+", parts[-1])):
        parts.pop()
    t = re.sub(r"(?<=[a-z])-(?=\d)", " ", " ".join(parts))
    for a, b in ABBR:
        t = re.sub(a, b, t)
    return " ".join(ROMAN.get(w, w) for w in norm(t).split())


def fingerprint(company: str, title: str) -> str:
    """Same company (legal suffixes aside) and the same role: one record, however many boards or reposts carry it."""
    key = company_key(company) + "|" + title_key(title)
    return hashlib.sha1(key.encode()).hexdigest()[:16]


def job_id(company: str, title: str) -> str:
    return slug(f"{company} {title}", 80)
