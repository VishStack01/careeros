"""Scam and bad-faith posting check.

Rule-based on purpose: each warning quotes the words that triggered it, so the person can judge
it, and nothing is sent to a model. The rules live in data/scam_rules.json, shared with the dashboard.
A "high" level stops auto-apply (see evaluation.apply_gate); "caution" only shows a badge.
"""

from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path

RULES_FILE = Path(__file__).resolve().parent / "data" / "scam_rules.json"
LEVELS = ("ok", "caution", "high")
_ATS_MAIL = re.compile(r"@(greenhouse|lever|ashbyhq|workday|smartrecruiters|workable|recruitee|teamtailor|icims|jobvite)\.", re.I)


@lru_cache(maxsize=1)
def rules() -> list[dict]:
    data = json.loads(RULES_FILE.read_text(encoding="utf-8"))
    return [dict(r, rx=re.compile(r["pattern"], re.I)) for r in data["rules"]]


def _text(job: dict) -> str:
    parts = [job.get(k) for k in ("title", "jd", "posting", "description", "salary", "url", "applyUrl", "note")]
    return "\n".join(str(p) for p in parts if p)[:80000]


def check(job: dict) -> dict:
    """{"level": "ok"|"caution"|"high", "reasons": [{"id", "level", "why", "quote"}]}. Never raises."""
    text = _text(job or {})
    found: list[dict] = []
    if text:
        for r in rules():
            m = r["rx"].search(text)
            if not m:
                continue
            quote = m.group(0).strip()
            if r["id"] == "free-mail" and _ATS_MAIL.search(quote):
                continue
            found.append({"id": r["id"], "level": r["level"], "why": r["why"], "quote": quote[:120]})
    level = "high" if any(f["level"] == "high" for f in found) else "caution" if found else "ok"
    # Three or more cautions together are a strong pattern: treat them as high.
    if level == "caution" and len(found) >= 3:
        level = "high"
    return {"level": level, "reasons": found}

