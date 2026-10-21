"""Clichés and filler in cover notes, screening answers and outreach.

    careeros writing-check note.txt [--banned "leverage,synergy"]

A recruiter reads hundreds of notes that open with "I am writing to express my
interest" and close with "I believe I would be a great fit". This check flags
those lines, plus words that make a note sound machine-written, so the draft
gets rewritten around one specific proof point instead. It warns; it never
rewrites anything itself.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass

# (pattern, why, what to do instead)
PHRASES = [
    (r"\bI am writing to (express|apply|convey)\b", "a stock opener", "open with their problem or your proof point"),
    (r"\b(I am|I'm) (excited|thrilled|delighted) to apply\b", "a stock opener", "say what you'd work on there"),
    (r"\bI believe I (would be|am) a (great|perfect|strong|good) fit\b", "a claim with no proof", "show the fit with one result"),
    (r"\bperfect (fit|match|candidate)\b", "a claim with no proof", "show the fit with one result"),
    (r"\bpassionate about\b", "filler", "name what you built"),
    (r"\bresults[- ]driven\b|\bdetail[- ]oriented\b|\bself[- ]starter\b|\bgo[- ]getter\b|\bteam player\b|\bhard[- ]working\b", "an unprovable adjective", "replace it with something you did"),
    (r"\bfast[- ]paced (environment|world|team)\b", "filler", "cut it"),
    (r"\b(think|thinking) outside the box\b|\bhit the ground running\b|\bgame[- ]changer\b|\bmove the needle\b", "a cliché", "say it plainly"),
    (r"\bleverag(e|ed|es|ing)\b", "jargon", "use 'use'"),
    (r"\bspearhead(ed|ing|s)?\b", "jargon", "use 'led' or 'started'"),
    (r"\bsynerg(y|ies|istic)\b", "jargon", "cut it"),
    (r"\bcutting[- ]edge\b|\bstate[- ]of[- ]the[- ]art\b|\bworld[- ]class\b|\bbest[- ]in[- ]class\b", "hype", "name the actual thing"),
    (r"\bdelve\b|\btapestry\b|\btestament to\b|\bin today's (fast[- ]paced|digital|ever[- ]changing)\b|\bever[- ]evolving\b|\bnavigat(e|ing) the complexities\b",
     "sounds machine-written", "rewrite it in your own words"),
    (r"\bseamless(ly)?\b|\brobust\b|\bsynergize\b|\bholistic\b", "vague", "say what it does or how well"),
    (r"\bresponsible for\b", "describes a duty, not a result", "say what you did and what changed"),
    (r"\bThank you for (your time and )?consideration\b", "a stock closer", "end with one clear ask"),
    (r"\bI look forward to hearing from you\b", "a stock closer", "end with one clear ask"),
]


@dataclass
class Finding:
    phrase: str
    why: str
    instead: str
    line: int

    def to_dict(self) -> dict:
        return asdict(self)


def check(text: str, banned: list[str] | None = None) -> list[Finding]:
    out: list[Finding] = []
    lines = (text or "").splitlines() or [""]
    rules = list(PHRASES) + [(rf"\b{re.escape(w)}\w*\b", "on your banned-words list", "use your own word") for w in (banned or []) if w.strip()]
    for n, line in enumerate(lines, 1):
        spans: list[tuple[int, int]] = []
        for rx, why, instead in rules:
            for m in re.finditer(rx, line, re.I):
                if any(a <= m.start() and m.end() <= b for a, b in spans):
                    continue  # already flagged as part of a longer phrase
                spans.append(m.span())
                out.append(Finding(m.group(0), why, instead, n))
    if text.count("!") > 1:
        out.append(Finding("!", f"{text.count('!')} exclamation marks", "keep at most one", 0))
    if text.count("—") > 2:
        out.append(Finding("—", f"{text.count('—')} long dashes", "use commas or full stops", 0))
    words = re.findall(r"[A-Za-z']+", text)
    if words and sum(1 for w in words if w.lower() in ("i", "i'm", "i've", "my", "me")) / len(words) > 0.09:
        out.append(Finding("I / my", "the note is mostly about you", "talk about their problem first", 0))
    return out


def specific(text: str) -> bool:
    """Does the note carry at least one concrete proof point (a number or a named thing you built)?"""
    return bool(re.search(r"\d", text or "")) or bool(re.search(r"\b(built|shipped|launched|designed|automated|cut|grew|reduced)\b", text or "", re.I))
