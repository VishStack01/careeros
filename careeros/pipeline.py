"""The scout run: fetch every board on the watchlist, gate every role, store the result."""

from __future__ import annotations

import tomllib
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from .gates import apply_decision
from .models import REGIONS, iso
from .settings import Settings
from .sources import SCOUTS, FetchError
from .store import Store


@dataclass
class RunReport:
    started_at: str
    finished_at: str = ""
    scanned: int = 0
    added: int = 0
    skipped: int = 0
    known: int = 0
    errors: list[str] = field(default_factory=list)
    kept: list[dict] = field(default_factory=list)

    def summary(self) -> str:
        best = self.kept[0] if self.kept else None
        tail = f" Best new role: {best['title']} at {best['company']}." if best else " No new role passed every gate."
        return f"Scanned {self.scanned} listings: {self.added} kept, {self.skipped} skipped, {self.known} already known.{tail}"


def load_watchlist(path: str | Path) -> list[dict]:
    data = tomllib.loads(Path(path).read_text(encoding="utf-8"))
    return data.get("boards", [])


def run(store: Store, settings: Settings, boards: list[dict], record_skips: bool = True, now: datetime | None = None) -> RunReport:
    now = now or datetime.now(timezone.utc)
    rep = RunReport(started_at=iso(now))
    for b in boards:
        scout = SCOUTS.get(b.get("ats", "").lower())
        if not scout:
            rep.errors.append(f"Unknown ATS '{b.get('ats')}' for {b.get('company')}")
            continue
        try:
            jobs = scout(b["token"], b.get("company"))
        except FetchError as e:
            rep.errors.append(str(e))
            continue
        for job in jobs:
            rep.scanned += 1
            if store.applied_recently(job.company, settings.reapply_cooldown_days):
                continue
            d = apply_decision(job, settings, now)
            # Only log skips for roles in your field; unrelated listings are noise.
            role_ok = next((c.passed for c in d.checks if c.gate == "Role"), False)
            if not d.kept and not (record_skips and role_ok):
                continue
            status, _ = store.add_job(job)
            if status == "known":
                rep.known += 1
            elif d.kept:
                rep.added += 1
                rep.kept.append({"title": job.title, "company": job.company, "region": job.region, "priority": job.priority})
            else:
                rep.skipped += 1
    rep.kept.sort(key=lambda k: (REGIONS.get(k["region"], 9), not k["priority"]))
    rep.finished_at = iso(datetime.now(timezone.utc))
    store.set("runs", rep.started_at.replace(":", "").replace("-", ""), {
        "startedAt": rep.started_at, "finishedAt": rep.finished_at, "scanned": rep.scanned,
        "added": rep.added, "skipped": rep.skipped, "summary": rep.summary(),
        **({"error": "; ".join(rep.errors)[:500]} if rep.errors and not rep.scanned else {}),
    })
    return rep
