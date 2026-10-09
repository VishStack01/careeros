"""Core data types shared by every stage of the pipeline."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone

# Every stage a role can be in. The order of the first seven is the funnel.
FUNNEL = ("found", "ready", "approved", "applied", "screen", "interview", "offer")
CLOSED = ("rejected", "withdrawn")
STAGES = FUNNEL + CLOSED + ("skipped",)

# Where a kept role sits in the priority order (lower is better).
REGIONS = {"remote-global": 0, "remote-india": 1, "south-india": 2}


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def iso(dt: datetime | None) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ") if dt else ""


@dataclass
class Check:
    """One gate's verdict on one role, with the exact text that decided it.

    Storing the quote is what makes every keep/skip decision auditable: you can
    read the sentence from the posting instead of trusting the agent.
    """

    gate: str
    passed: bool
    value: str = ""
    quote: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class Job:
    """A posting, normalised from whichever source it came from."""

    company: str
    title: str
    url: str
    source: str
    location: str = ""
    work_mode: str = ""  # "remote" | "hybrid" | "onsite" | ""
    description: str = ""
    posted_at: str = ""  # ISO 8601, UTC
    apply_by: str = ""  # YYYY-MM-DD
    salary_text: str = ""
    req_id: str = ""
    applicants: int | None = None
    raw: dict = field(default_factory=dict, repr=False)

    # Filled in by the pipeline.
    id: str = ""
    stage: str = "found"
    region: str = ""
    priority: bool = False
    checks: list[Check] = field(default_factory=list)
    found_at: str = ""

    def to_record(self) -> dict:
        """The document shape the dashboard reads (camelCase, JSON-safe)."""
        failed = [c for c in self.checks if not c.passed]
        rec = {
            "company": self.company,
            "title": self.title,
            "url": self.url,
            "source": self.source,
            "location": self.location,
            "workMode": self.work_mode,
            "postedAt": self.posted_at,
            "applyBy": self.apply_by,
            "salary": self.salary_text,
            "reqId": self.req_id,
            "region": self.region,
            "priority": self.priority,
            "stage": self.stage,
            "fitBand": "pending",
            "foundAt": self.found_at or iso(utcnow()),
            "checks": [c.to_dict() for c in self.checks],
            "timeline": [{"at": self.found_at or iso(utcnow()), "event": f"Found on {self.source}"}],
        }
        exp = next((c for c in self.checks if c.gate == "Experience"), None)
        if exp:
            rec["experience"] = exp.value
        if self.applicants is not None:
            rec["applicants"] = self.applicants
        if self.stage == "skipped" and failed:
            first = failed[0]
            rec["skip"] = {
                "gate": " · ".join(c.gate for c in failed),
                "reason": first.value + (f' The posting says: "{first.quote}"' if first.quote else ""),
                "wouldChange": "",
            }
        return rec
