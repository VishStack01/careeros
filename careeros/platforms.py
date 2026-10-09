"""The job-platform registry (config/platforms.toml) and which ones to visit this run."""

from __future__ import annotations

import tomllib
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

DEFAULT = Path(__file__).resolve().parent.parent / "config" / "platforms.toml"
ROTATIONS = 3  # platforms that aren't every-run are split into this many groups


def load(path: str | Path | None = None) -> list[dict]:
    p = Path(path) if path else DEFAULT
    return tomllib.loads(p.read_text(encoding="utf-8")).get("platform", [])


def for_run(platforms: list[dict], run_index: int | None = None) -> list[dict]:
    """Every-run platforms plus one rotation group of the rest.

    Feed platforms are skipped (the scan reads them) and alert-only platforms
    are skipped (the Gmail tracker reads their emails)."""
    if run_index is None:
        now = datetime.now(timezone.utc)
        run_index = (now.timetuple().tm_yday * 8 + now.hour // 3)
    agent = [p for p in platforms if p.get("access") in ("fetch", "login") and p.get("kind") != "company-list"]
    rest = [p for p in agent if not p.get("every_run")]
    group = run_index % ROTATIONS
    return [p for p in agent if p.get("every_run")] + [p for i, p in enumerate(rest) if i % ROTATIONS == group]


def summary(platforms: list[dict]) -> dict:
    return {
        "total": len(platforms),
        "byAccess": dict(Counter(p.get("access", "") for p in platforms)),
        "byKind": dict(Counter(p.get("kind", "") for p in platforms)),
        "lowCompetition": sum(1 for p in platforms if p.get("competition") == "low"),
    }
