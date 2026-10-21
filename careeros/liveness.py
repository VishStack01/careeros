"""Is this posting still open? A zero-token check before anyone spends time on it.

    careeros liveness <url> [<url> ...]

Order of evidence:
1. The hiring system's own API, when the URL is a Greenhouse, Lever, Ashby,
   SmartRecruiters or Workable posting: the job is listed (open) or not (closed).
2. The page itself: HTTP 404/410 means gone; a closure banner ("no longer
   accepting applications", "this job has expired") means closed; an Apply
   control means open.
3. Anything else is "uncertain", never a guess.

Closure phrases and the API-first order follow career-ops (MIT,
github.com/career-ops-hq/career-ops); the code is our own.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import asdict, dataclass
from typing import Callable
from urllib.parse import parse_qs, urlparse

from .sources.http import FetchError, get_json, get_text


@dataclass
class Liveness:
    status: str  # open | closed | uncertain
    reason: str
    evidence: str = ""
    via: str = ""  # api | page

    def to_dict(self) -> dict:
        return asdict(self)


_HARD_CLOSED = [
    r"job (?:is )?no longer available", r"\bno longer accepting applications\b", r"this job has expired", r"job posting has expired",
    r"\b(?:job|position|role|posting|opening|vacancy|requisition|listing)\b[\s\S]{0,60}?(?<!application )(?<!form )has been filled\b(?!\s+out)",
    r"this (?:position|role|job) (?:is )?no longer (?:open|available|active)", r"this (?:job|role|position)(?: listing)? is closed\b(?!-)",
    r"\bjob (?:listing )?not found\b", r"\bapplications? (?:are |have been |is )?(?:now )?closed\b", r"\bthe job you are looking for (?:is no longer|has been)",
    r"\bposition (?:has been )?(?:closed|filled)\b(?!-)", r"we(?:'re| are) no longer hiring for this",
]
_CLOSED = re.compile("|".join(_HARD_CLOSED), re.I)
_APPLY = re.compile(r"<(?:a|button|input)[^>]{0,300}(?:apply|submit application|bewerben|postuler)[^>]{0,200}>|>\s*apply(?: now| for this job)?\s*<", re.I)


def _norm(text: str) -> str:
    text = text.replace("’", "'").replace("‘", "'").replace("“", '"').replace("”", '"')
    text = "".join(c for c in unicodedata.normalize("NFD", text) if unicodedata.category(c) != "Mn")
    return re.sub(r"\s+", " ", text)


def ats_api(url: str) -> tuple[str, str] | None:
    """(kind, api url) for postings whose hiring system has a public per-job or per-board API."""
    u = urlparse(url)
    host, parts = u.netloc.lower(), [p for p in u.path.split("/") if p]
    q = parse_qs(u.query)
    if host.endswith("greenhouse.io") and len(parts) >= 3 and parts[-2] == "jobs" and parts[-1].isdigit():
        return "greenhouse", f"https://boards-api.greenhouse.io/v1/boards/{parts[-3]}/jobs/{parts[-1]}"
    if host.endswith("greenhouse.io") and "for" in q and "token" in q and q["token"][0].isdigit():  # embedded application form
        return "greenhouse", f"https://boards-api.greenhouse.io/v1/boards/{q['for'][0]}/jobs/{q['token'][0]}"
    if host in ("jobs.lever.co", "jobs.eu.lever.co") and len(parts) >= 2:
        api = "api.eu.lever.co" if ".eu." in host else "api.lever.co"
        return "lever", f"https://{api}/v0/postings/{parts[0]}/{parts[1]}"
    if host == "jobs.ashbyhq.com" and len(parts) >= 2:
        return "ashby", f"https://api.ashbyhq.com/posting-api/job-board/{parts[0]}#{parts[1]}"
    if host == "jobs.smartrecruiters.com" and len(parts) >= 2:
        jid = parts[1].split("-")[0]
        return "smartrecruiters", f"https://api.smartrecruiters.com/v1/companies/{parts[0]}/postings/{jid}"
    if host == "apply.workable.com" and len(parts) >= 3 and parts[1] == "j":
        return "workable", f"https://apply.workable.com/api/v2/accounts/{parts[0]}/jobs/{parts[2]}"
    return None


def check(url: str, fetch_json: Callable = get_json, fetch_text: Callable = get_text) -> Liveness:
    api = ats_api(url)
    if api:
        kind, endpoint = api
        try:
            if kind == "ashby":
                board, jid = endpoint.split("#")
                data = fetch_json(board)
                ids = {str(j.get("id")) for j in (data or {}).get("jobs", [])}
                if ids:
                    return Liveness("open", "Listed on the company's Ashby board.", via="api") if jid in ids else \
                        Liveness("closed", "No longer listed on the company's Ashby board.", via="api")
            else:
                data = fetch_json(endpoint)
                if kind == "smartrecruiters" and isinstance(data, dict) and data.get("active") is False:
                    return Liveness("closed", "SmartRecruiters marks the posting inactive.", via="api")
                if isinstance(data, dict) and (data.get("id") or data.get("title") or data.get("text") or data.get("shortcode")):
                    return Liveness("open", f"Listed by the {kind.title()} API.", via="api")
        except FetchError as e:
            # Lever's API sometimes 404s postings its page still serves; let the page decide for Lever.
            if e.status in (404, 410) and kind != "lever":
                return Liveness("closed", f"The {kind.title()} API no longer has this posting (HTTP {e.status}).", via="api")
    try:
        html = fetch_text(url)
    except FetchError as e:
        if e.status in (404, 410):
            return Liveness("closed", f"The page is gone (HTTP {e.status}).", via="page")
        return Liveness("uncertain", f"Couldn't load the page ({e.status or 'network error'}).", via="page")
    text = _norm(re.sub(r"<script[\s\S]*?</script>|<style[\s\S]*?</style>", " ", html))
    plain = re.sub(r"<[^>]+>", " ", text)
    m = _CLOSED.search(plain)
    if m:
        a, b = max(0, m.start() - 60), min(len(plain), m.end() + 60)
        return Liveness("closed", "The page says the posting is closed.", plain[a:b].strip(), via="page")
    if _APPLY.search(text):
        return Liveness("open", "The page shows an Apply control.", via="page")
    return Liveness("uncertain", "The page loaded but shows neither an Apply control nor a closure notice.", via="page")
