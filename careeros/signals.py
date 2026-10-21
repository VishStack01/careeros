"""Signals about a posting itself, separate from whether it fits you.

* work_authorization: "US citizens only", "security clearance", "must be
  authorized to work in the UK" and similar. For someone applying from India
  these are hard blockers unless the country named is India.
* agency: a recruiter posting for an unnamed client.
* legitimacy: is this likely a real, active opening? Observations, never
  accusations: age, re-listing, a closure banner, vague or contradictory
  requirements, pay transparency, agency postings.
* RepostHistory: remembers every listing across scans, so a role that is taken
  down and listed again is noticed.
* archetype: which kind of AI role this is.

Ideas adapted from career-ops (MIT, github.com/career-ops-hq/career-ops):
posting legitimacy (its Block G), repost detection, the work-authorization
blocker and archetype detection. The code here is our own.
"""

from __future__ import annotations

import gzip
import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

from . import tags
from .dedupe import company_key
from .textutil import norm, quote_around

# ---------------------------------------------------------------- work authorization

_COUNTRY = (r"(?P<{name}>U\.?S\.?A?|United States(?: of America)?|America|U\.?K\.?|United Kingdom|Great Britain|Britain|"
            r"Canada|Australia|New Zealand|Germany|France|Netherlands|Ireland|Spain|Poland|Singapore|Japan|Israel|"
            r"Switzerland|Sweden|Denmark|Norway|Finland|the EU|EU|European Union|Europe|EEA|India|Brazil|Mexico)")
_CITIZEN = re.compile(
    r"\b(?:(?P<a>U\.?S\.?|United States|American|U\.?K\.?|British|Canadian|Australian|EU|Israeli|Singapore|Indian) citizens?(?:hip)?"
    r"(?: (?:is |are )?(?:only|required|is a requirement|needed))?"
    r"|must (?:be|hold) (?:a )?(?P<b>U\.?S\.?|United States|American|U\.?K\.?|British|Canadian|Australian|Indian) (?:citizen|national|passport)"
    r"|citizenship (?:in|of) (?:the )?(?P<d>U\.?S\.?|United States|U\.?K\.?|Canada|Australia|India) (?:is )?required)",
    re.I)
_CLEARANCE = re.compile(
    r"\b(?:active |current |valid )?(?:security|secret|top[- ]secret|TS/SCI|TS|SC|DV|public trust|NV1|NV2|baseline) clearance\b"
    r"|\b(?:eligible|ability) (?:for|to obtain|to hold) (?:a |an )?(?:U\.?S\.? )?(?:government |security )?clearance\b|\bclearable\b",
    re.I)
_LOCAL_AUTH = re.compile(
    r"\b(?:must|should|will need to|need to|required to|candidates must|applicants must)\s+(?:be\s+|have\s+)?(?:legally\s+)?"
    r"(?:authori[sz]ed|eligible|entitled|permitted|able)\s+to\s+work\s+(?:in|within|from)\s+(?:the\s+)?" + _COUNTRY.format(name="c1") +
    r"|\b(?:the\s+)?right to work in (?:the\s+)?" + _COUNTRY.format(name="c2") +
    r"|\bwork(?:ing)? (?:authori[sz]ation|permit|rights) (?:in|for) (?:the\s+)?" + _COUNTRY.format(name="c3") + r"\b(?! is not required)",
    re.I)
_NO_SPONSOR = re.compile(
    r"\b(?:not|no|unable to|cannot|can't|won't|will not|do not|does not|don't|doesn't)\s+(?:currently\s+)?(?:provide|offer|support|sponsor|be able to sponsor)?\s*"
    r"(?:visa|work permit|employment)?\s*sponsor(?:ship|ing)?\b|\bwithout (?:the need for |requiring )?(?:current or future )?(?:visa |employer )?sponsorship\b"
    r"|\bsponsorship (?:is )?not (?:available|offered|provided)\b",
    re.I)


def _country(raw: str | None) -> str:
    c = re.sub(r"[.\s]", "", (raw or "")).lower()
    if c in ("us", "usa", "unitedstates", "unitedstatesofamerica", "america", "american"):
        return "US"
    if c in ("uk", "unitedkingdom", "greatbritain", "britain", "british"):
        return "UK"
    if c in ("theeu", "eu", "europeanunion", "europe", "eea"):
        return "EU"
    if c in ("india", "indian"):
        return "India"
    return (raw or "").strip().title()


def work_authorization(text: str) -> dict:
    """{"kind": citizenship|clearance|local|no-sponsorship, "country", "quote"} for the strongest
    requirement in the posting, or {} when it names none."""
    text = text or ""
    for kind, rx in (("citizenship", _CITIZEN), ("clearance", _CLEARANCE), ("local", _LOCAL_AUTH)):
        for m in rx.finditer(text):
            g = m.groupdict()
            country = _country(next((v for v in g.values() if v), None)) if g else ""
            if kind == "clearance":
                country = "US" if re.search(r"\bU\.?S\.?\b|TS/SCI|public trust", m.group(0)) else ""
            return {"kind": kind, "country": country, "quote": quote_around(text, *m.span())}
    m = _NO_SPONSOR.search(text)
    if m:
        return {"kind": "no-sponsorship", "country": "", "quote": quote_around(text, *m.span())}
    return {}


def work_auth_blocks(wa: dict, loc: str) -> bool:
    """True when the requirement rules out someone applying from India.
    Citizenship and clearance block unless they name India; a local work-authorization
    requirement blocks unless it names India. "No sponsorship" alone doesn't block remote
    roles open to India (no visa is needed to work remotely from India)."""
    if not wa:
        return False
    if wa["kind"] in ("citizenship", "clearance", "local"):
        return wa.get("country") != "India" and loc not in ("remote-india", "south", "india")
    if wa["kind"] == "no-sponsorship":
        return loc == "abroad"
    return False


# ---------------------------------------------------------------- agency postings

_AGENCY = re.compile(
    r"\b(?:on behalf of (?:our|a|one of our) (?:valued |esteemed )?clients?|our client(?:'s)? (?:is|are|a|an|has|,)|for (?:one of )?our clients?\b"
    r"|we are (?:a |an )?(?:leading |global |specialist )?(?:recruitment|recruiting|staffing|talent acquisition|hiring) (?:agency|firm|partner|company|consultancy)"
    r"|(?:recruitment|staffing) agency\b|confidential (?:client|company)\b)",
    re.I)


def agency(text: str) -> str:
    m = _AGENCY.search(text or "")
    return quote_around(text, *m.span()) if m else ""


# ---------------------------------------------------------------- archetypes

ARCHETYPES = [
    ("Forward deployed", r"\bforward[- ]deployed\b|\bfde\b|customer[- ]facing engineer|field engineer|deployment engineer|deployed engineer"),
    ("Agentic & automation", r"\bagents?\b|\bagentic\b|\bautomation\b|\borchestration\b|\bmulti[- ]agent\b|\bworkflow"),
    ("AI platform & LLMOps", r"\bllmops\b|\bmlops\b|\bml platform\b|\bai platform\b|\binference\b|\bevals?\b|\bobservability\b|\bai infra"),
    ("Solutions architect", r"\bsolutions? (?:architect|engineer)\b|\bsales engineer\b|\bpre[- ]?sales\b|\bai architect\b"),
    ("AI product", r"\bproduct manager\b|\bproduct owner\b|\bapm\b|\bai product\b|\bproduct designer\b|\bdesign engineer\b"),
    ("AI transformation", r"\btransformation\b|\badoption\b|\benablement\b|\bchange management\b"),
    ("Applied AI & LLM engineering", r"\b(?:ai|ml|llm|genai|gen ai|applied ai|machine learning|nlp|rag)\b"),
]


_AI = re.compile(r"\b(?:ai|a\.i\.|ml|llms?|genai|gen ai|generative|machine learning|nlp|agents?|agentic|rag|deep learning|computer vision)\b", re.I)


def archetype(title: str, text: str = "") -> str:
    """Which kind of AI role this is ("" for roles that aren't AI roles). The title decides when it can.
    Otherwise the posting's opening decides, but only on repeated evidence (two or more mentions),
    so one stray "workflow" doesn't label a role."""
    head = (text or "")[:2500]
    for name in ("Forward deployed", "Agentic & automation", "AI platform & LLMOps"):  # AI-native titles on their own
        rx = dict(ARCHETYPES)[name]
        if re.search(rx, title or "", re.I) and (name != "Agentic & automation" or re.search(r"\bagent", title or "", re.I)):
            return name
    if not _AI.search(title or "") and len(_AI.findall(head)) < 2:
        return ""
    for name, rx in ARCHETYPES:
        if re.search(rx, title or "", re.I):
            return name
    hits = [(len(re.findall(rx, head, re.I)), -i, name) for i, (name, rx) in enumerate(ARCHETYPES)]
    best = max(hits)
    return best[2] if best[0] >= 2 else ""


# ---------------------------------------------------------------- legitimacy

_ENTRY_TITLE = re.compile(r"\b(?:junior|jr\.?|entry[- ]level|associate|graduate|new grad|fresher|intern(?:ship)?|trainee|apprentice)\b", re.I)


def contradictions(title: str, facts: dict, text: str = "") -> list[str]:
    out = []
    e = facts.get("expMin")
    if e is not None and e >= 4 and _ENTRY_TITLE.search(title or ""):
        out.append(f"Asks for {e:g}+ years in an entry-level title.")
    if e is not None and e >= 3 and re.search(r"\bfreshers? (?:are )?(?:welcome|can apply|eligible)\b", text or "", re.I):
        out.append(f"Welcomes freshers but asks for {e:g}+ years.")
    return out


def legitimacy(title: str, text: str, facts: dict, posted_at: str = "", reposts: dict | None = None,
               now: datetime | None = None) -> dict:
    """{"tier": high|caution|suspicious, "label", "signals": [{"signal", "status": good|mixed|concern|info, "note", "quote"}]}.
    Separate from fit: a role can fit you perfectly and still be worth checking first."""
    now = now or datetime.now(timezone.utc)
    sig = []

    def add(signal, status, note, quote=""):
        sig.append({"signal": signal, "status": status, "note": note, "quote": (quote or "")[:220]})

    try:
        dt = datetime.fromisoformat((posted_at or "").replace("Z", "+00:00"))
        days = (now - (dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc))).days
    except ValueError:
        days = None
    if days is None:
        add("Age", "mixed", "The posting doesn't show when it was listed.")
    elif days < 30:
        add("Age", "good", f"Listed {max(days, 0)} days ago.")
    elif days <= 60:
        add("Age", "mixed", f"Open for {days} days.")
    else:
        add("Age", "concern", f"Open for {days} days; long-open roles are often evergreen or forgotten.")
    if facts.get("closedQuote"):
        add("Open", "concern", "The posting says it's closed.", facts["closedQuote"])
    n = (reposts or {}).get("count", 0)
    if n >= 2:
        add("Re-listed", "concern", f"Taken down and listed again {n} times since {(reposts or {}).get('since', '')[:10]}.")
    elif n == 1:
        add("Re-listed", "mixed", f"Taken down and listed again once since {(reposts or {}).get('since', '')[:10]}.")
    skills = tags.skills(title, text, limit=20)
    if len(skills) >= 3:
        add("Specific", "good", f"Names concrete tools: {', '.join(skills[:5])}.")
    elif len(text or "") < 600 and not skills:
        add("Specific", "concern", "A short, generic description with no concrete tools or tasks.")
    else:
        add("Specific", "mixed", "Few concrete tools named.")
    for c in contradictions(title, facts, text):
        add("Consistent", "concern", c, facts.get("expQuote", ""))
    if facts.get("salaryHigh"):
        add("Pay shown", "good", "The posting states pay.", facts.get("salaryQuote", ""))
    else:
        add("Pay shown", "info", "No pay stated (common, and legal in India).")
    ag = facts.get("agencyQuote") or agency(text)
    if ag:
        add("Employer named", "mixed", "A recruiter posting for an unnamed client: the end employer isn't disclosed.", ag)
    concerns = sum(1 for s in sig if s["status"] == "concern")
    mixed = sum(1 for s in sig if s["status"] == "mixed")
    tier = "suspicious" if concerns >= 2 else "caution" if concerns == 1 or mixed >= 3 or ag else "high"
    return {"tier": tier, "label": {"high": "Looks real", "caution": "Check before applying", "suspicious": "Suspicious"}[tier],
            "signals": sig}


# ---------------------------------------------------------------- repost history

def title_identity(company: str, title: str) -> str:
    """Same company and the same SET of title words. Word order and punctuation may change between
    listings of one role; a different city, level or team word makes it a different requisition."""
    words = sorted(set(re.findall(r"[a-z0-9+#]+", norm(re.sub(r"\([^)]*\)", " ", title or "")))))
    return company_key(company) + "|" + " ".join(words)


class RepostHistory:
    """Every listing seen, by title identity: {key: [{"id", "url", "first", "last"}]}.

    A re-listing is a listing of the same role that first appeared after an earlier listing had
    already disappeared. Two listings open at the same time are parallel openings, not a repost."""

    def __init__(self, path: str | Path, window_days: int = 90):
        self.path, self.window = Path(path), window_days
        self.data: dict[str, list[dict]] = {}
        if self.path.exists():
            try:
                with gzip.open(self.path, "rt", encoding="utf-8") as f:
                    self.data = json.load(f)
            except (OSError, ValueError):
                self.data = {}

    def observe(self, records: list[dict], now: datetime | None = None) -> None:
        today = (now or datetime.now(timezone.utc)).strftime("%Y-%m-%d")
        for r in records:
            listings = self.data.setdefault(title_identity(r["company"], r["title"]), [])
            hit = next((x for x in listings if x["url"] == r["url"] or x["id"] == r["id"]), None)
            if hit:
                hit["last"] = today
            else:
                listings.append({"id": r["id"], "url": r["url"], "first": today, "last": today})

    def reposts(self, company: str, title: str, url: str) -> dict:
        listings = sorted(self.data.get(title_identity(company, title), []), key=lambda x: x["first"])
        cur = next((x for x in listings if x["url"] == url), None)
        if not cur:
            return {"count": 0}
        cutoff = (datetime.strptime(cur["first"], "%Y-%m-%d") - timedelta(days=self.window)).strftime("%Y-%m-%d")
        n, since, prev_last = 0, "", None
        for x in listings:
            if x["first"] < cutoff or x["first"] > cur["first"]:
                continue
            if prev_last is not None and x["first"] > prev_last:
                n += 1
            since = since or x["first"]
            prev_last = max(prev_last or x["last"], x["last"])
        return {"count": n, "since": since, "firstSeen": listings[0]["first"]} if n else {"count": 0, "firstSeen": cur["first"]}

    def prune(self, now: datetime | None = None, keep_days: int = 150) -> None:
        cutoff = ((now or datetime.now(timezone.utc)) - timedelta(days=keep_days)).strftime("%Y-%m-%d")
        for k in list(self.data):
            self.data[k] = [x for x in self.data[k] if x["last"] >= cutoff]
            if not self.data[k]:
                del self.data[k]

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with gzip.open(self.path, "wt", encoding="utf-8") as f:
            json.dump(self.data, f, separators=(",", ":"))
