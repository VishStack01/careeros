"""Requirement extraction from posting text.

Every extractor returns the value *and* the sentence it came from, so the gate
that uses it can show its working. The rules here encode lessons from real
postings:

* Headers lie. A card that says "1 year" can hide "2+ years of development" in
  the description. We read the whole text and take the highest requirement.
* "Nice to have" years are not requirements.
* "Remote" in a description is weak evidence ("remote-controlled robots");
  structured fields and the location string win.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone

from .textutil import quote_around

# ---------------------------------------------------------------- experience

_WORDNUM = {
    "zero": 0, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7,
    "eight": 8, "nine": 9, "ten": 10, "eleven": 11, "twelve": 12, "fifteen": 15, "twenty": 20,
}
_NUM = r"(\d{1,2}(?:\.\d)?|" + "|".join(_WORDNUM) + r")"
_YRS = r"(?:years?|yrs?|year\(s\))"
_NOT_EXPERIENCE_AFTER = re.compile(r"^\W{0,3}(?:ago|old|of age|in business|of history|warranty|anniversary)", re.I)
_EXPERIENCE_CONTEXT = re.compile(
    r"experience|\bexp\b|working|work\b|industry|professional|hands[- ]on|building|developing|shipping|"
    r"writing|designing|in (?:a |an )?(?:software|engineering|product|design|ml|ai|data|backend|frontend)",
    re.I,
)
_PREFERRED_HEADING = re.compile(
    r"nice[- ]to[- ]have|preferred|bonus|good[- ]to[- ]have|desirable|plus points|would be a plus|we'd love|ideal(?:ly)?",
    re.I,
)
_HEADING_LINE = re.compile(r"^\s*[A-Za-z][A-Za-z /&'’-]{2,60}:?\s*$")

_PATTERNS = [
    ("range", re.compile(_NUM + r"\s*(?:-|–|—|to)\s*" + _NUM + r"\s*\+?\s*" + _YRS, re.I)),
    ("plus", re.compile(_NUM + r"\s*\+\s*" + _YRS, re.I)),
    ("min", re.compile(r"(?:at least|minimum(?: of)?|min\.?|more than|over|no less than)\s+" + _NUM + r"\s*\+?\s*" + _YRS, re.I)),
    ("ormore", re.compile(_NUM + r"\s+(?:or more|plus)\s+" + _YRS, re.I)),
    ("bare", re.compile(r"(?<![\d.])" + _NUM + r"\s*" + _YRS + r"(?:'|’)?", re.I)),
]

_FRESHER = re.compile(
    r"\bfreshers?\b|\bnew[- ]grad(?:uate)?s?\b|\brecent graduates?\b|\bentry[- ]level\b|"
    r"\bno (?:prior )?experience (?:is )?(?:required|needed|necessary)\b|\b20\d\d (?:batch|graduates|pass[- ]?outs?)\b|"
    r"\bany \(new grads ok\)",
    re.I,
)
_NOT_FRESHER = re.compile(r"\bnot (?:a |for |open to )?(?:freshers?|entry[- ]level|new grads?)\b", re.I)


def _num(tok: str) -> float:
    tok = tok.lower()
    return float(_WORDNUM[tok]) if tok in _WORDNUM else float(tok)


@dataclass
class Mention:
    years: float
    kind: str
    preferred: bool
    quote: str


@dataclass
class ExperienceReq:
    min_years: float | None  # highest required minimum found, None if not stated
    fresher_ok: bool | None  # True if text welcomes freshers, False if it rules them out
    quote: str = ""
    mentions: list[Mention] = field(default_factory=list)

    def describe(self) -> str:
        if self.min_years is None:
            return "Fresher welcome" if self.fresher_ok else "Not stated"
        y = int(self.min_years) if self.min_years == int(self.min_years) else self.min_years
        return f"{y}+ years" if y else "Fresher (0 years)"


def _section_flags(text: str) -> list[tuple[int, bool]]:
    """(offset, preferred?) for each heading-like line, so a match can look up its section."""
    flags: list[tuple[int, bool]] = []
    pos = 0
    for line in text.splitlines(keepends=True):
        stripped = line.strip()
        if stripped and (_HEADING_LINE.match(stripped) or stripped.endswith(":")) and len(stripped) <= 70:
            flags.append((pos, bool(_PREFERRED_HEADING.search(stripped))))
        pos += len(line)
    return flags


def extract_experience(text: str, header: str = "") -> ExperienceReq:
    """Find the experience requirement in `header` + `text`.

    `header` is a short structured field such as Internshala's "1 year(s)" card;
    it is read like any other mention, so a stricter body wins.
    """
    full = (header + "\n" + text) if header else (text or "")
    sections = _section_flags(full)
    taken: list[tuple[int, int]] = []
    mentions: list[Mention] = []
    for kind, rx in _PATTERNS:
        for m in rx.finditer(full):
            s, e = m.span()
            if any(s < te and e > ts for ts, te in taken):
                continue
            after = full[e:e + 40]
            if _NOT_EXPERIENCE_AFTER.match(after):
                continue
            ctx = full[max(0, s - 60):e + 80]
            if kind == "bare" and not _EXPERIENCE_CONTEXT.search(ctx):
                continue
            years = _num(m.group(1))
            if years > 30:
                continue
            quote = quote_around(full, s, e)
            heading_pref = False
            for off, pref in sections:
                if off <= s:
                    heading_pref = pref
                else:
                    break
            preferred = heading_pref or bool(re.search(r"preferred|nice to have|a plus|bonus|ideally", quote, re.I))
            mentions.append(Mention(years, kind, preferred, quote))
            taken.append((s, e))

    required = [m for m in mentions if not m.preferred]
    top = max(required, key=lambda m: m.years) if required else None

    fresher_ok: bool | None = None
    if _NOT_FRESHER.search(full):
        fresher_ok = False
    elif _FRESHER.search(full):
        fresher_ok = True

    if top:
        return ExperienceReq(top.years, fresher_ok, top.quote, mentions)
    fq = ""
    m = _NOT_FRESHER.search(full) or _FRESHER.search(full)
    if m:
        fq = quote_around(full, *m.span())
    return ExperienceReq(None, fresher_ok, fq, mentions)


# ---------------------------------------------------------------- seniority

_SENIOR_TITLE = re.compile(
    r"\b(senior|sr\.?|staff|principal|lead|head|director|vp|vice president|chief|distinguished|architect)\b", re.I
)
_JUNIOR_TITLE = re.compile(
    r"\b(junior|jr\.?|associate|intern|internship|trainee|graduate|entry[- ]level|fresher|new grad|apprentice)\b", re.I
)


def title_seniority(title: str) -> str:
    """'senior', 'junior' or '' for a job title."""
    if _SENIOR_TITLE.search(title or ""):
        return "senior"
    if _JUNIOR_TITLE.search(title or ""):
        return "junior"
    return ""


# ---------------------------------------------------------------- work mode

_REMOTE_STRONG = re.compile(
    r"\bfully remote\b|\bremote[- ]first\b|\b100% remote\b|\bremote[- ]only\b|\bwork from (?:home|anywhere)\b|\bwfh\b|"
    r"\bthis (?:role|position|job) is (?:fully )?remote\b|\bremote (?:position|role|job|opportunity)\b",
    re.I,
)
_HYBRID = re.compile(r"\bhybrid\b", re.I)
_ONSITE = re.compile(r"\bon[- ]?site\b|\bin[- ]office\b|\bwork from office\b|\bwfo\b|\bin[- ]person\b", re.I)


def work_mode(structured: str = "", location: str = "", text: str = "") -> str:
    s = (structured or "").lower().replace("-", "").replace("_", "")
    if s in ("remote",):
        return "remote"
    if s in ("hybrid",):
        return "hybrid"
    if s in ("onsite", "inoffice", "office"):
        return "onsite"
    loc = location or ""
    if re.search(r"\bremote\b|\banywhere\b|\bwork from home\b", loc, re.I):
        return "remote"
    if _HYBRID.search(loc):
        return "hybrid"
    if _ONSITE.search(loc):
        return "onsite"
    if _REMOTE_STRONG.search(text or ""):
        return "remote"
    if _HYBRID.search(text or ""):
        return "hybrid"
    if _ONSITE.search(text or ""):
        return "onsite"
    return ""


# ---------------------------------------------------------------- remote scope

_WORLD = re.compile(r"\banywhere\b|\bworld ?wide\b|\bglobal(?:ly)?\b|\bany (?:country|location|timezone)\b|\beverywhere\b", re.I)
_INDIA = re.compile(r"\bindia\b|\bIST\b|\bbengaluru\b|\bbangalore\b|\bhyderabad\b|\bchennai\b", re.I)
_APAC = re.compile(r"\bapac\b|\bapj\b|\basia[- ]pacific\b|\basia\b", re.I)
_US_CS = re.compile(r"\bUS\b|\bU\.S\.\b|\bUSA\b")
_US = re.compile(r"\bunited states\b|\bnorth america\b|\bnamer\b|\bcanada\b|\bus[- ]based\b|\bus citizens?\b|\bmust (?:reside|live) in the us\b", re.I)
_EU = re.compile(r"\bemea\b|\beurope(?:an)?\b|\bEU\b|\bunited kingdom\b|\buk[- ]only\b|\bCET\b", re.I)
_AMERICAS = re.compile(r"\bamericas\b|\blatam\b|\blatin america\b|\bsouth america\b", re.I)
_TZ_RANGE = re.compile(
    r"(?:GMT|UTC)\s*([+-]\s?\d{1,2}(?::?\d{2})?)\s*(?:to|-|–|and|through)\s*(?:GMT|UTC)?\s*([+-]\s?\d{1,2}(?::?\d{2})?)", re.I
)


def _tz(s: str) -> float:
    s = s.replace(" ", "")
    sign = -1 if s.startswith("-") else 1
    s = s.lstrip("+-")
    if ":" in s:
        h, m = s.split(":")
    elif len(s) > 2:
        h, m = s[:-2], s[-2:]
    else:
        h, m = s, "0"
    return sign * (int(h) + int(m) / 60)


@dataclass
class RemoteScope:
    india_eligible: bool | None  # None = posting doesn't say
    scope: str  # "worldwide" | "india" | "apac" | "us" | "europe" | "timezone" | ""
    quote: str = ""


def remote_scope(location: str, text: str) -> RemoteScope:
    """Can someone living in India take this remote role?"""
    blob = f"{location}\n{text or ''}"
    m = _TZ_RANGE.search(blob)
    if m:
        a, b = sorted((_tz(m.group(1)), _tz(m.group(2))))
        ok = a <= 5.5 <= b
        return RemoteScope(ok, "timezone", quote_around(blob, *m.span()))
    for rx, scope in ((_INDIA, "india"), (_WORLD, "worldwide"), (_APAC, "apac")):
        m = rx.search(location or "")
        if m:
            return RemoteScope(True, scope, location)
    for rx, scope in ((_US, "us"), (_EU, "europe"), (_AMERICAS, "americas")):
        m = rx.search(location or "")
        if m:
            return RemoteScope(False, scope, location)
    if _US_CS.search(location or ""):
        return RemoteScope(False, "us", location)
    for rx, scope in ((_INDIA, "india"), (_WORLD, "worldwide"), (_APAC, "apac")):
        m = rx.search(text or "")
        if m:
            return RemoteScope(True, scope, quote_around(text, *m.span()))
    for rx, scope in ((_US, "us"), (_EU, "europe")):
        m = rx.search(text or "")
        if m and re.search(r"only|must|reside|based in|located in|authori[sz]ed", quote_around(text, *m.span()), re.I):
            return RemoteScope(False, scope, quote_around(text, *m.span()))
    return RemoteScope(None, "", "")


# ---------------------------------------------------------------- salary

_MULT = {"k": 1e3, "m": 1e6, "": 1.0}
_PERIOD = r"(?:\s*(?:/|per|a)\s*(year|yr|annum|month|mo|hour|hr))?"
_LPA = re.compile(r"(\d+(?:\.\d+)?)\s*(?:-|–|to)\s*(\d+(?:\.\d+)?)\s*(?:lpa|lakhs?(?: per annum)?|l\.?p\.?a\.?)\b", re.I)
_LPA_ONE = re.compile(r"(\d+(?:\.\d+)?)\s*(?:lpa|lakhs? per annum)\b", re.I)
_MONEY = re.compile(
    r"(₹|rs\.?\s?|inr\s?|\$|usd\s?)\s*([\d,]+(?:\.\d+)?)\s*([kKmM])?\s*(?:-|–|to)\s*(?:₹|rs\.?\s?|inr\s?|\$|usd\s?)?\s*([\d,]+(?:\.\d+)?)\s*([kKmM])?"
    + _PERIOD,
    re.I,
)
_MONEY_ONE = re.compile(r"(₹|rs\.?\s?|inr\s?|\$|usd\s?)\s*([\d,]+(?:\.\d+)?)\s*([kKmM])?" + _PERIOD, re.I)


@dataclass
class Salary:
    low_lpa: float
    high_lpa: float
    currency: str
    period: str
    quote: str = ""

    def describe(self) -> str:
        def f(x: float) -> str:
            return f"{x:.1f}".rstrip("0").rstrip(".")
        return f"{f(self.low_lpa)}–{f(self.high_lpa)} LPA" if self.low_lpa != self.high_lpa else f"{f(self.high_lpa)} LPA"


def _period_mult(p: str | None) -> tuple[float, str]:
    p = (p or "year").lower()
    if p in ("month", "mo"):
        return 12.0, "month"
    if p in ("hour", "hr"):
        return 2112.0, "hour"  # 8 h x 22 days x 12 months
    return 1.0, "year"


def parse_salary(text: str, usd_inr: float = 88.0) -> Salary | None:
    """Parse the first pay range in `text` into lakhs per annum (LPA)."""
    if not text:
        return None
    m = _LPA.search(text)
    if m:
        lo, hi = float(m.group(1)), float(m.group(2))
        return Salary(lo, hi, "INR", "year", quote_around(text, *m.span()))
    m = _MONEY.search(text)
    if m:
        cur = "USD" if ("$" in m.group(1) or "usd" in m.group(1).lower()) else "INR"
        lo = float(m.group(2).replace(",", "")) * _MULT[(m.group(3) or "").lower()]
        hi = float(m.group(4).replace(",", "")) * _MULT[(m.group(5) or m.group(3) or "").lower()]
        mult, period = _period_mult(m.group(6))
        rate = usd_inr if cur == "USD" else 1.0
        return Salary(lo * mult * rate / 1e5, hi * mult * rate / 1e5, cur, period, quote_around(text, *m.span()))
    m = _LPA_ONE.search(text)
    if m:
        v = float(m.group(1))
        return Salary(v, v, "INR", "year", quote_around(text, *m.span()))
    m = _MONEY_ONE.search(text)
    if m:
        cur = "USD" if ("$" in m.group(1) or "usd" in m.group(1).lower()) else "INR"
        v = float(m.group(2).replace(",", "")) * _MULT[(m.group(3) or "").lower()]
        if cur == "INR" and v < 10000 and not m.group(3):
            return None  # "₹ 500" style noise
        mult, period = _period_mult(m.group(4))
        rate = usd_inr if cur == "USD" else 1.0
        lpa = v * mult * rate / 1e5
        return Salary(lpa, lpa, cur, period, quote_around(text, *m.span()))
    return None


# ---------------------------------------------------------------- facts bundle

def facts(text: str, header: str = "", location: str = "", salary_text: str = "", usd_inr: float = 88.0) -> dict:
    """Everything the gates need, extracted once from the full posting.

    The India feed stores these instead of whole descriptions, so personal
    filters can run later without re-downloading every posting."""
    exp = extract_experience(text, header)
    scope = remote_scope(location, text)
    sal = parse_salary(salary_text, usd_inr) or parse_salary(text, usd_inr)
    out = {
        "expMin": exp.min_years, "expQuote": exp.quote, "fresherOk": exp.fresher_ok,
        "scope": scope.scope, "scopeEligible": scope.india_eligible, "scopeQuote": scope.quote,
        "closedQuote": closed_signal(text), "applicants": applicants(text),
    }
    if sal:
        out.update({"salaryLow": round(sal.low_lpa, 2), "salaryHigh": round(sal.high_lpa, 2), "salaryQuote": sal.quote})
    return out


# ---------------------------------------------------------------- misc signals

_APPLICANTS = re.compile(r"(\d[\d,]*)\+?\s+applicants", re.I)
_CLOSED = re.compile(
    r"no longer accepting applications|position (?:has been )?filled|this job (?:is|has) (?:closed|expired)|"
    r"applications? (?:are |is )?(?:now )?closed|job (?:has )?expired",
    re.I,
)
_APPLY_BY = re.compile(r"apply by\s*(\d{1,2})\s*([A-Za-z]{3})[a-z]*\.?\s*['’]?\s*(\d{2,4})", re.I)
_MONTHS = {m: i for i, m in enumerate(["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], 1)}
_POSTED = re.compile(
    r"(?:posted|reposted)\s+(just now|today|yesterday|few hours ago|an? (hour|day|week|month) ago|(\d+)\s+(hour|day|week|month)s?\s+ago)",
    re.I,
)


def applicants(text: str) -> int | None:
    m = _APPLICANTS.search(text or "")
    return int(m.group(1).replace(",", "")) if m else None


def closed_signal(text: str) -> str:
    m = _CLOSED.search(text or "")
    return quote_around(text, *m.span()) if m else ""


def apply_by(text: str) -> date | None:
    m = _APPLY_BY.search(text or "")
    if not m:
        return None
    day, mon, yr = int(m.group(1)), _MONTHS.get(m.group(2).lower()[:3]), int(m.group(3))
    if not mon:
        return None
    if yr < 100:
        yr += 2000
    try:
        return date(yr, mon, day)
    except ValueError:
        return None


def posted_from_relative(text: str, now: datetime | None = None) -> datetime | None:
    """Turn 'Posted 3 days ago' into a timestamp."""
    now = now or datetime.now(timezone.utc)
    m = _POSTED.search(text or "")
    if not m:
        return None
    phrase = m.group(1).lower()
    if phrase in ("just now", "few hours ago", "today"):
        return now - timedelta(hours=3 if phrase != "just now" else 0)
    if phrase == "yesterday":
        return now - timedelta(days=1)
    n = int(m.group(3)) if m.group(3) else 1
    unit = (m.group(4) or m.group(2) or "day").lower()
    delta = {"hour": timedelta(hours=n), "day": timedelta(days=n), "week": timedelta(weeks=n), "month": timedelta(days=30 * n)}[unit]
    return now - delta
