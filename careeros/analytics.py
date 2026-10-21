"""How the search is going: the funnel, response times, whether the scores mean
anything, and which skills keep coming up that you can't yet prove.

    careeros stats [--jobs DIR] [--days 30] [--json]
    careeros calibrate [--jobs DIR]
    careeros gaps [--jobs DIR] [--brain brain/brain.json]

`--jobs` reads a folder of job JSON documents (an ArtifactData export); without
it the local database is used. Small samples are labelled as such: a rate from
six applications is an anecdote, not a finding.
"""

from __future__ import annotations

import re
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from statistics import median

FLOW = ["found", "ready", "approved", "applied", "screen", "interview", "offer"]
RESPONDED = ("screen", "interview", "offer")
MIN_SAMPLE = 10


def _dt(s):
    try:
        d = datetime.fromisoformat(str(s).replace("Z", "+00:00"))
        return d if d.tzinfo else d.replace(tzinfo=timezone.utc)
    except (TypeError, ValueError):
        return None


def _reached(j: dict) -> set[str]:
    """Stages a role has passed through (a rejected role still counts as applied, and screened if it was)."""
    st = j.get("stage") or "found"
    got = set()
    if st in FLOW:
        got.update(FLOW[: FLOW.index(st) + 1])
    if j.get("appliedAt"):
        got.update(FLOW[: FLOW.index("applied") + 1])
    for s in ("screen", "interview", "offer"):
        if j.get(f"{s}At"):
            got.update(FLOW[: FLOW.index(s) + 1])
    return got


def _rate(a: int, b: int) -> str:
    return f"{a}/{b} ({a / b:.0%})" if b else "0/0"


def stats(jobs: list[dict], now: datetime | None = None, days: int = 30) -> dict:
    now = now or datetime.now(timezone.utc)
    since = now - timedelta(days=days)
    recent = [j for j in jobs if (_dt(j.get("foundAt")) or _dt(j.get("appliedAt")) or now) >= since]
    funnel = Counter()
    for j in recent:
        for s in _reached(j):
            funnel[s] += 1
    applied = [j for j in recent if j.get("appliedAt")]
    responded = [j for j in applied if _reached(j) & set(RESPONDED)]
    rejected = [j for j in applied if j.get("stage") == "rejected"]
    waits = []
    for j in applied:
        a, r = _dt(j.get("appliedAt")), _dt(j.get("firstResponseAt") or j.get("screenAt") or j.get("rejectedAt"))
        if a and r and r >= a:
            waits.append((r - a).total_seconds() / 86400)
    speed = []
    for j in applied:
        p, a = _dt(j.get("postedAt")), _dt(j.get("appliedAt"))
        if p and a and a >= p:
            speed.append((a - p).total_seconds() / 3600)

    def split(key):
        out = defaultdict(lambda: [0, 0])
        for j in applied:
            k = j.get(key) or "unknown"
            out[k][0] += 1
            out[k][1] += 1 if _reached(j) & set(RESPONDED) else 0
        return {k: {"applied": a, "responded": r, "rate": _rate(r, a), "small": a < MIN_SAMPLE} for k, (a, r) in sorted(out.items(), key=lambda x: -x[1][0])}

    skips = Counter()
    for j in recent:
        if j.get("stage") == "skipped":
            for g in str((j.get("skip") or {}).get("gate") or "unknown").split(" · "):
                skips[g] += 1
    return {
        "days": days, "roles": len(recent), "funnel": {s: funnel[s] for s in FLOW},
        "applied": len(applied), "responded": len(responded), "rejected": len(rejected),
        "responseRate": _rate(len(responded), len(applied)), "smallSample": len(applied) < MIN_SAMPLE,
        "medianDaysToResponse": round(median(waits), 1) if waits else None,
        "medianHoursPostToApply": round(median(speed), 1) if speed else None,
        "byRegion": split("region"), "bySource": split("source"), "byArchetype": split("archetype"),
        "appliedVia": dict(Counter(j.get("appliedVia") or "unknown" for j in applied)),
        "skipsByGate": dict(skips.most_common(8)),
    }


BANDS = [("4.5+", 4.5, 5.01), ("4.0-4.4", 4.0, 4.5), ("3.5-3.9", 3.5, 4.0), ("under 3.5", 0, 3.5)]


def calibrate(jobs: list[dict]) -> dict:
    """Outcomes by score band, for applications that were scored. If 4.5+ roles
    don't get more replies than 4.0-4.4 ones, the scoring needs a look."""
    rows = []
    for label, lo, hi in BANDS:
        js = [j for j in jobs if j.get("appliedAt") and isinstance((j.get("evaluation") or {}).get("score"), (int, float))
              and lo <= j["evaluation"]["score"] < hi]
        resp = [j for j in js if _reached(j) & set(RESPONDED)]
        inter = [j for j in js if _reached(j) & {"interview", "offer"}]
        rows.append({"band": label, "applied": len(js), "responded": len(resp), "interviews": len(inter),
                     "responseRate": _rate(len(resp), len(js)), "small": len(js) < MIN_SAMPLE})
    scored = sum(r["applied"] for r in rows)
    note = ""
    if scored < 2 * MIN_SAMPLE:
        note = f"Only {scored} scored application(s) so far. Read these as early signals, not results."
    else:
        hi, mid = rows[0], rows[1]
        if hi["applied"] >= MIN_SAMPLE and mid["applied"] >= MIN_SAMPLE and hi["responded"] / hi["applied"] <= mid["responded"] / mid["applied"]:
            note = "4.5+ roles aren't getting more replies than 4.0-4.4 ones: the scoring may be rewarding the wrong things."
    unscored = sum(1 for j in jobs if j.get("appliedAt") and not (j.get("evaluation") or {}).get("score"))
    return {"bands": rows, "scored": scored, "unscored": unscored, "note": note}


def _norm_skill(s: str) -> str:
    return re.sub(r"[^a-z0-9+#.]", "", (s or "").lower())


def gaps(jobs: list[dict], brain: dict | None, limit: int = 10) -> list[dict]:
    """Skills most often asked for in roles you kept, that your brain has no evidence for.
    From the posting tags (skills) and from evaluations' missing or partial requirements."""
    have = set()
    for s in (brain or {}).get("skills", []):
        if s.get("evidence"):
            have.add(_norm_skill(s.get("name", "")))
            have.update(_norm_skill(a) for a in s.get("aliases", []))
    asked: Counter = Counter()
    examples: dict[str, list[str]] = defaultdict(list)
    partial: Counter = Counter()
    for j in jobs:
        if j.get("stage") == "skipped":
            continue
        role = f"{j.get('title', '')} at {j.get('company', '')}"
        names = set(j.get("skills") or [])
        for r in (j.get("evaluation") or {}).get("requirements", []):
            if r.get("match") in ("missing", "partial") and r.get("importance") in ("critical", "high", "meaningful"):
                names.add(r.get("requirement", ""))
                if r.get("match") == "partial":
                    partial[r.get("requirement", "")] += 1
        for n in names:
            if n and _norm_skill(n) not in have:
                asked[n] += 1
                if len(examples[n]) < 3:
                    examples[n].append(role)
    return [{"skill": k, "roles": v, "partly": partial.get(k, 0), "examples": examples[k]} for k, v in asked.most_common(limit)]
