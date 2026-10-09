"""The hallucination gate for tailored resumes.

A tailored resume is written as JSON where every bullet names the brain claims
it is built from:

  {"summary": "...", "skills": ["Python", ...],
   "bullets": [{"text": "Cut ticket triage time 40% with an LLM router", "refs": ["ach-triage"]}]}

`check()` blocks the resume if any bullet:
  * has no refs, or refs a claim that doesn't exist;
  * describes PLANNED work as done;
  * contains a number that doesn't appear in the referenced claims;
  * names a tool from your brain that the referenced claims don't use;
  * lists a skill that isn't in the brain.
It also warns on banned words from your voice profile, "responsible for", and
low metric density. Model review (the Reviewer skill) runs after this; this
deterministic pass catches the failures a model can talk itself past.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from .brain import claims as brain_claims

_NUMBER = re.compile(r"(?<![A-Za-z])(\d[\d,]*(?:\.\d+)?)\s*(%|x|k|m|\+|lakh|cr|crore|ms|s\b|hours?|days?|weeks?|users?)?", re.I)
_DEFAULT_BANNED = ["leverage", "leveraged", "spearhead", "spearheaded", "synergy", "results-driven", "dynamic", "passionate", "rockstar", "ninja", "guru", "cutting-edge"]


@dataclass
class Report:
    blocking: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    metric_density: float = 0.0

    @property
    def ok(self) -> bool:
        return not self.blocking


def _numbers(text: str) -> set[str]:
    out = set()
    for m in _NUMBER.finditer(text or ""):
        n = m.group(1).replace(",", "")
        if re.fullmatch(r"(19|20)\d\d", n):
            continue  # years like 2024 are dates, not metrics
        out.add(n.rstrip("0").rstrip(".") if "." in n else n)
    return out


def check(resume: dict, brain: dict) -> Report:
    rep = Report()
    index = brain_claims(brain)
    known_tools = {t for c in index.values() for t in c.tools}
    skill_names = {s.get("name", "").lower() for s in brain.get("skills", [])}
    for s in brain.get("skills", []):
        skill_names.update(a.lower() for a in s.get("aliases", []))
    banned = [w.lower() for w in (brain.get("voice", {}).get("banned_words") or _DEFAULT_BANNED)]

    bullets = resume.get("bullets", [])
    with_metric = 0
    for i, b in enumerate(bullets, 1):
        text = b.get("text", "")
        label = f"Bullet {i} (\"{text[:60]}{'…' if len(text) > 60 else ''}\")"
        refs = b.get("refs") or []
        if not refs:
            rep.blocking.append(f"{label}: no brain reference, so it can't be traced to anything real.")
            continue
        missing = [r for r in refs if r not in index]
        if missing:
            rep.blocking.append(f"{label}: refers to {', '.join(missing)}, which isn't in the brain.")
            continue
        claimset = [index[r] for r in refs]
        if any(c.status == "planned" for c in claimset) and not re.search(r"\b(building|planning|will|upcoming|in progress)\b", text, re.I):
            rep.blocking.append(f"{label}: describes planned work as if it were done.")
        source_text = " ".join(c.text for c in claimset)
        stray = _numbers(text) - _numbers(source_text)
        if stray:
            rep.blocking.append(f"{label}: the number(s) {', '.join(sorted(stray))} don't appear in the referenced claims.")
        if _numbers(text):
            with_metric += 1
        claim_tools = {t for c in claimset for t in c.tools}
        for tool in known_tools - claim_tools:
            if re.search(r"(?<![A-Za-z])" + re.escape(tool) + r"(?![A-Za-z])", text, re.I):
                rep.blocking.append(f"{label}: mentions {tool}, which the referenced claims don't use.")
        for w in banned:
            if re.search(r"\b" + re.escape(w) + r"(?:s|d|ed|ing)?\b", text, re.I):
                rep.warnings.append(f"{label}: uses '{w}', which is on your banned-words list.")
        if re.search(r"\bresponsible for\b", text, re.I):
            rep.warnings.append(f"{label}: 'responsible for' says what you were assigned, not what you did.")

    for sk in resume.get("skills", []):
        if sk.lower() not in skill_names:
            rep.blocking.append(f"Skill '{sk}' isn't in your brain's skill list.")

    rep.metric_density = with_metric / len(bullets) if bullets else 0.0
    if bullets and rep.metric_density < 0.6:
        rep.warnings.append(f"Only {rep.metric_density:.0%} of bullets contain a number; aim for 60% or more.")
    return rep
