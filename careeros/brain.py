"""The Career Brain: the single source of truth every application is built from.

Format (JSON, see brain/brain.example.json):

  identity    name, headline, location, links
  skills      [{name, proficiency 1-5, years, last_used, evidence: [ev-ids]}]
  experience  [{id, org, title, start, end, status, entries: [claim]}]
  projects    [{id, name, status, ...claim fields}]
  evidence    [{id, kind, ref, note}]
  stories     [{id, competency, situation, task, action, result, refs}]
  voice       {banned_words, preferred_verbs, samples}

A claim is {id, problem, action, tools, outcome, metrics: [{value, what}], evidence: [ev-ids], status}.
Status is one of PAST, CURRENT, IN_PROGRESS, PLANNED, RETIRED. Planned work can
never be written up as done.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

STATUSES = {"past", "current", "in_progress", "planned", "retired"}


@dataclass
class Claim:
    id: str
    kind: str  # "experience" | "project"
    parent: str  # org or project name
    status: str
    text: str  # everything the claim says, for number and tool checks
    tools: list[str]
    evidence: list[str]


def load(path: str | Path) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def claims(brain: dict) -> dict[str, Claim]:
    """Index every claim by id."""
    out: dict[str, Claim] = {}

    def add(c: dict, kind: str, parent: str, inherited_status: str):
        cid = c.get("id")
        if not cid:
            return
        metrics = " ".join(f"{m.get('value', '')} {m.get('what', '')}" for m in c.get("metrics", []))
        text = " ".join(str(c.get(k, "")) for k in ("problem", "action", "outcome", "summary", "name")) + " " + metrics
        out[cid] = Claim(
            id=cid, kind=kind, parent=parent,
            status=(c.get("status") or inherited_status or "past").lower(),
            text=text, tools=[t.lower() for t in c.get("tools", [])], evidence=list(c.get("evidence", [])),
        )

    for exp in brain.get("experience", []):
        for entry in exp.get("entries", []):
            add(entry, "experience", exp.get("org", ""), exp.get("status", ""))
    for proj in brain.get("projects", []):
        add(proj, "project", proj.get("name", ""), proj.get("status", ""))
    return out


def validate(brain: dict) -> list[str]:
    """Problems that would let an unprovable claim reach a resume."""
    problems: list[str] = []
    ev_ids = {e.get("id") for e in brain.get("evidence", [])}
    seen: set[str] = set()
    for cid, c in claims(brain).items():
        if cid in seen:
            problems.append(f"{cid}: duplicate id")
        seen.add(cid)
        if c.status not in STATUSES:
            problems.append(f"{cid}: unknown status '{c.status}'")
        if not c.evidence:
            problems.append(f"{cid}: no evidence linked; it can't be used on a resume until it has proof")
        for ev in c.evidence:
            if ev not in ev_ids:
                problems.append(f"{cid}: evidence '{ev}' isn't in the evidence vault")
    for s in brain.get("skills", []):
        if not s.get("evidence"):
            problems.append(f"skill '{s.get('name')}': no evidence linked")
        for ev in s.get("evidence", []):
            if ev not in ev_ids:
                problems.append(f"skill '{s.get('name')}': evidence '{ev}' isn't in the evidence vault")
    for exp in brain.get("experience", []):
        st = (exp.get("status") or "").lower()
        if st == "planned" and exp.get("end"):
            problems.append(f"{exp.get('org')}: planned role has an end date")
    return problems


def skill_years(brain: dict, skill: str) -> float | None:
    for s in brain.get("skills", []):
        if s.get("name", "").lower() == skill.lower() or skill.lower() in [a.lower() for a in s.get("aliases", [])]:
            return s.get("years")
    return None
