"""Search settings, loaded from TOML. Every field has a safe default."""

from __future__ import annotations

import tomllib
from dataclasses import dataclass, field
from pathlib import Path

DEFAULT_ROLE_KEYWORDS = [
    "ai", "a.i.", "artificial intelligence", "genai", "gen ai", "generative", "llm", "agent", "agentic",
    "machine learning", "ml", "mlops", "applied scientist", "nlp", "computer vision", "prompt",
    "automation", "forward deployed", "data scientist", "ai product", "conversational", "rag",
]


@dataclass
class LocationPolicy:
    south_india: str = "any"  # "any" | "remote" | "never"
    rest_of_india: str = "remote"  # "any" | "remote" | "never"
    abroad: str = "remote"  # "remote" | "never"
    # When a remote role abroad doesn't say who can apply: keep it for a
    # human check (True) or skip it (False).
    keep_unclear_remote: bool = True


@dataclass
class Settings:
    max_required_years: float = 1
    max_posting_age_days: int = 25
    ghost_after_days: int = 60
    priority_within_hours: int = 48
    salary_floor_lpa: float | None = 7.0
    usd_inr: float = 88.0
    role_keywords: list[str] = field(default_factory=lambda: list(DEFAULT_ROLE_KEYWORDS))
    title_exclude: list[str] = field(default_factory=list)
    dealbreakers: list[str] = field(default_factory=list)
    company_blocklist: list[str] = field(default_factory=list)
    allow_internships: bool = True
    location: LocationPolicy = field(default_factory=LocationPolicy)
    daily_cap: int = 8
    reapply_cooldown_days: int = 180

    @classmethod
    def load(cls, path: str | Path | None) -> "Settings":
        s = cls()
        if not path or not Path(path).exists():
            return s
        data = tomllib.loads(Path(path).read_text(encoding="utf-8"))
        search = data.get("search", data)
        for key in (
            "max_required_years", "max_posting_age_days", "ghost_after_days", "priority_within_hours",
            "salary_floor_lpa", "usd_inr", "role_keywords", "title_exclude", "dealbreakers",
            "company_blocklist", "allow_internships", "daily_cap", "reapply_cooldown_days",
        ):
            if key in search:
                setattr(s, key, search[key])
        loc = data.get("location", {})
        for key in ("south_india", "rest_of_india", "abroad", "keep_unclear_remote"):
            if key in loc:
                setattr(s.location, key, loc[key])
        if s.salary_floor_lpa in (0, "", None):
            s.salary_floor_lpa = None
        return s
