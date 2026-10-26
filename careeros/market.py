"""What the roles that pay your floor ask for, measured on the live feed.

    careeros market --feed feed/india.jsonl.gz --settings settings.json --resume resume.pdf

Takes every role in the feed that fits your target roles and experience limit,
splits it by pay (stated at or above your floor, estimated from public offer
data, below it, not known), counts the skills those well-paid roles ask for
and checks each against your resume. Missing skills are things to learn or to
show in a project, never words to paste into a resume you can't back up.
"""

from __future__ import annotations

import re
from collections import Counter
from pathlib import Path

from . import ats, paydata

_DEFAULT_ROLES = ["engineer", "developer", "sde", "swe", "ai", "ml", "machine learning", "forward deployed", "data scientist"]


def _kw(words: list[str]) -> re.Pattern:
    parts = [r"(?<![a-z0-9])" + re.escape(w.lower()) + r"(?:s|es)?(?![a-z0-9])" for w in words if str(w).strip()]
    return re.compile("|".join(parts) or r"(?!x)x", re.I)


def resume_text(path: str | Path) -> str:
    p = Path(path)
    return ats.pdf_text(p)[0] if p.suffix.lower() == ".pdf" else p.read_text(encoding="utf-8")


def pay_class(facts: dict, floor: float | None, company: str = "") -> str:
    hi, band = facts.get("salaryHigh"), facts.get("payBand") or paydata.band(company) or {}
    if floor is None:
        return "stated" if hi is not None else "unknown"
    if hi is not None:
        return "stated" if hi >= floor else "below"
    if band and band.get("low", 0) >= floor:
        return "estimated"
    return "unknown"


def analyze(records: list[dict], settings: dict, resume: str = "", top: int = 20) -> dict:
    roles = _kw([r for r in settings.get("targetRoles") or []] + _DEFAULT_ROLES)
    excl = _kw(settings.get("titleExclude") or [])
    max_y = float(settings.get("maxRequiredYears") if settings.get("maxRequiredYears") is not None else 1)
    floor = settings.get("salaryFloorLpa")
    floor = float(floor) if floor not in (None, "", 0) else None
    funnel = Counter()
    paid, pay_hist, companies = [], Counter(), Counter()
    for r in records:
        funnel["openings"] += 1
        t, f = r.get("title") or "", r.get("facts") or {}
        if not roles.search(t) or excl.search(t):
            continue
        funnel["your roles"] += 1
        e = f.get("expMin")
        if (e is not None and e > max_y) or (f.get("senior") and max_y < 3):
            continue
        funnel["your experience"] += 1
        if f.get("loc") in ("remote-excluded", "abroad"):
            continue
        funnel["open to you"] += 1
        pc = pay_class(f, floor, r.get("company", ""))
        funnel[f"pay {pc}"] += 1
        hi = f.get("salaryHigh")
        if hi is not None:
            b = "under 10" if hi < 10 else "10–15" if hi < 15 else "15–25" if hi < 25 else "25–50" if hi < 50 else "50+"
            pay_hist[b] += 1
        if pc in ("stated", "estimated"):
            paid.append(r)
            companies[r.get("company", "")] += 1
    skill_counts = Counter(s for r in paid for s in set((r.get("tags") or {}).get("skills") or []))
    n = len(paid) or 1
    skills = [{"skill": s, "roles": c, "share": round(c / n, 3), "onResume": ats._has(s, resume) if resume else None}
              for s, c in skill_counts.most_common(top)]
    order = ["openings", "your roles", "your experience", "open to you", "pay stated", "pay estimated", "pay below", "pay unknown"]
    return {
        "floorLpa": floor,
        "funnel": {k: funnel.get(k, 0) for k in order},
        "payStated": {k: pay_hist.get(k, 0) for k in ("under 10", "10–15", "15–25", "25–50", "50+")},
        "skills": skills,
        "gaps": [s["skill"] for s in skills if s["onResume"] is False],
        "companies": [{"company": c, "roles": k} for c, k in companies.most_common(25)],
        "rolesAtFloor": len(paid),
    }
