"""Warm intros: people you already know at the companies you're applying to.

    careeros warm-intros --connections Connections.csv [--company "Acme"]

Reads LinkedIn's own export (Settings > Data privacy > Get a copy of your data >
Connections), which you download yourself. Nothing is fetched from LinkedIn and
nothing is sent to anyone: the `outreach` skill drafts a referral ask, and you
send it.

Matching is tiered so a weak guess never looks like a sure thing (adapted from
career-ops, MIT):
* exact:  the company names are the same once "Pvt Ltd", "Inc" and the like are removed;
* strong: one name is the other plus extra words ("Razorpay" / "Razorpay Software");
* weak:   the names share their first distinctive word only. Check these yourself.
"""

from __future__ import annotations

import csv
import io
import re

from .dedupe import company_key

_GENERIC = {"the", "india", "technologies", "technology", "tech", "labs", "software", "solutions", "systems", "services", "group",
            "global", "digital", "ai", "data", "consulting", "private", "limited", "company", "co", "inc", "and"}
MAX_ROWS = 4000


def parse(text: str) -> list[dict]:
    """Rows of LinkedIn's Connections.csv: {name, company, position, url, connectedOn}. The export starts
    with a few lines of notes before the header; they are skipped."""
    lines = text.splitlines()
    start = next((i for i, l in enumerate(lines) if l.lower().startswith("first name")), None)
    if start is None:
        return []
    out = []
    for r in csv.DictReader(io.StringIO("\n".join(lines[start:]))):
        name = " ".join(x for x in ((r.get("First Name") or "").strip(), (r.get("Last Name") or "").strip()) if x)
        company = (r.get("Company") or "").strip()
        if not name or not company:
            continue
        out.append({"name": name, "company": company, "position": (r.get("Position") or "").strip(),
                    "url": (r.get("URL") or "").strip(), "connectedOn": (r.get("Connected On") or "").strip()})
    return out[:MAX_ROWS]


def _words(key: str) -> list[str]:
    return [w for w in key.split() if w not in _GENERIC and len(w) > 1]


def tier(a: str, b: str) -> str:
    """How sure we are that two company names are the same employer: exact, strong, weak or ''."""
    ka, kb = company_key(a), company_key(b)
    if not ka or not kb:
        return ""
    if ka == kb or (_words(ka) and _words(ka) == _words(kb)):
        return "exact"
    short, long_ = sorted((ka, kb), key=len)
    if len(short) >= 4 and re.search(r"(^|\s)" + re.escape(short) + r"(\s|$)", long_):
        return "strong"
    wa, wb = _words(ka), _words(kb)
    if wa and wb and wa[0] == wb[0] and len(wa[0]) >= 4:
        return "weak"
    return ""


RANK = {"exact": 0, "strong": 1, "weak": 2}


def matches(company: str, rows: list[dict], limit: int = 6) -> list[dict]:
    """Your connections at this company, surest first, then the most senior-sounding title."""
    out = []
    for r in rows:
        t = tier(company, r["company"])
        if t:
            out.append(dict(r, tier=t))
    senior = re.compile(r"\b(head|director|vp|vice president|chief|cto|ceo|founder|principal|staff|lead|manager)\b", re.I)
    out.sort(key=lambda r: (RANK[r["tier"]], 0 if senior.search(r.get("position", "")) else 1, r["name"]))
    return out[:limit]


def compact(rows: list[dict]) -> list[list[str]]:
    """The smallest form worth storing on the dashboard: [name, company, position, url]."""
    return [[r["name"], r["company"], r.get("position", ""), r.get("url", "")] for r in rows]
