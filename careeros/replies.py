"""Sort a reply from a company: what it is and what stage it moves the role to.

    careeros classify-reply email.txt

A deterministic first pass for the `tracker` skill. It returns the kind, the
stage the role should move to (if any) and the sentence that decided it, so the
user can check. When nothing matches clearly it says "unclear" and the tracker
lists the email for the user instead of guessing. Email text is data: nothing in
it is followed as an instruction.
"""

from __future__ import annotations

import re

from .textutil import quote_around

# Checked in order; the first kind whose pattern matches wins.
RULES = [
    ("offer", "offer", r"\b(pleased|happy|delighted) to (extend|offer)\b|\boffer letter\b|\bjob offer\b|\bcompensation package\b"),
    ("rejection", "rejected", r"\b(decided|chosen|elected) (not )?to (move|proceed|go) forward with (other|another)\b|\bnot (be )?(moving|proceeding) forward\b|"
                              r"\bwill not be (moving|proceeding)\b|\bunfortunately\b[^.]{0,120}\b(not|other candidates)\b|\bposition has been filled\b|"
                              r"\bnot (a|the right) (fit|match)\b at this time|\bregret to inform\b|\bwe have decided to pursue\b"),
    ("interview", "interview", r"\b(schedule|book|set up|arrange)\b[^.]{0,60}\b(interview|technical round|onsite|panel)\b|\binterview (invitation|invite)\b|"
                               r"\binvite you (to|for) (an? )?(interview|technical|onsite|panel)\b"),
    ("assessment", "screen", r"\b(assessment|coding (test|challenge)|take[- ]home|hackerrank|codility|hackerearth|testgorilla|codesignal)\b"),
    ("recruiter-reply", "screen", r"\b(your (profile|background|application) (stood out|caught|looks|is a))\b|\bwould love to (chat|connect|learn more)\b|"
                                  r"\b(are you|would you be) (available|open|interested)\b|\bquick (call|chat)\b|\b(schedule|book) a (call|chat)\b|\bcalendly\.com\b|\bpick a (time|slot)\b"),
    ("confirmation", None, r"\b(thank you|thanks) for (applying|your application|your interest)\b|\bapplication (has been )?(received|submitted)\b|"
                           r"\bwe('ve| have) received your application\b"),
]


def classify(subject: str, body: str) -> dict:
    """{"kind", "stage", "quote"}; kind "unclear" when nothing matches."""
    text = f"{subject or ''}\n{body or ''}"
    for kind, stage, rx in RULES:
        m = re.search(rx, text, re.I)
        if m:
            # A confirmation that also says "unfortunately" etc. is caught by the earlier rules; one that
            # only thanks you for applying stays a confirmation.
            return {"kind": kind, "stage": stage, "quote": quote_around(text, m.start(), m.end())}
    return {"kind": "unclear", "stage": None, "quote": ""}


def apply_to_job(job: dict, result: dict, at: str) -> dict:
    """The job fields to change for a classified reply. Never moves a role backwards."""
    order = ["found", "ready", "approved", "applied", "screen", "interview", "offer"]
    stage, cur = result.get("stage"), job.get("stage") or "found"
    patch: dict = {}
    if stage == "rejected" and cur not in ("offer", "withdrawn"):
        patch = {"stage": "rejected", "rejectedAt": at, "rejection": {"quote": result.get("quote", "")}}
    elif stage in order and cur in order and order.index(stage) > order.index(cur):
        patch = {"stage": stage, f"{stage}At": at}
    if result.get("kind") == "assessment":
        patch["assessment"] = {"at": at, "quote": result.get("quote", "")}
    if job.get("appliedAt") and patch.get("stage") in ("screen", "interview", "offer", "rejected") and not job.get("firstResponseAt"):
        patch["firstResponseAt"] = at
    return patch
