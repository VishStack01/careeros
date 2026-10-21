"""Scored evaluations: one role, scored 1-5 against your Career Brain, with a verdict.

An evaluation is written by an agent (the `evaluate` skill) and checked here
before it reaches the dashboard or the apply runner. The checks are what make
the score trustworthy:

* The overall score is a judgment, not a formula, but it must sit inside the
  range of its five dimension scores.
* 4.0 is the apply line. Below it CareerOS recommends against applying, and
  auto-apply skips the role unless you press "Apply anyway".
* Confidence is computed from the evidence, never typed in: High only when all
  five dimensions are supported and no open question remains.
* Requirement importance comes from the posting. A "stated" requirement needs a
  verbatim quote from the posting; an "inferred" one (market knowledge) can never
  be critical or high, so a guess can't manufacture a gap.
* A "strong" match needs evidence from your brain, and planned work never counts.
* Every critical or high requirement you only partly meet, or miss, needs an
  interview risk and a mitigation.

Structure, bands and tier rules follow career-ops's A-H evaluation
(MIT, github.com/career-ops-hq/career-ops); the code is our own.

  careeros eval-check EVAL.json [--job JOB.json] [--jd JD.txt] [--brain brain.json] [--md REPORT.md]
"""

from __future__ import annotations

import re
import unicodedata
from datetime import datetime, timezone

APPLY_LINE = 4.0

DIMENSIONS = {
    "cvMatch": "Match with your experience",
    "northStar": "Fits the roles you want",
    "comp": "Pay",
    "culture": "Company and culture",
    "redFlags": "Red flags (5 = none)",
}
STATUSES = ("supported", "partial", "unknown")
IMPORTANCE = ("critical", "high", "meaningful", "preferred", "low_signal")
TIERS = ("stated", "structural", "inferred")
MATCHES = ("strong", "partial", "missing", "na")
MATCH_LABEL = {"strong": "Strong", "partial": "Partial", "missing": "Missing", "na": "N/A"}
COMPANY_TYPES = (
    "Public big tech / mature tech", "Growth-stage startup", "Early-stage startup", "Enterprise / traditional corporate",
    "Agency / outsourcing / consulting", "Local SMB / service business", "Sales / commission-heavy", "Recruiter / staffing listing",
    "Government / academic / nonprofit", "Open-source / community", "Unknown",
)
RELIABILITY = ("high", "medium", "low")
ROW_BUDGET = 12

BANDS = [  # (lowest score, band, decision letter, fit band, label)
    (4.5, "strong", "A", "strong", "Strong match. Apply now."),
    (4.0, "apply", "A", "good", "Good match. Worth applying."),
    (3.5, "consider", "B", "stretch", "Decent, not ideal. Apply only for a specific reason."),
    (0.0, "skip", "F", "weak", "Weak match. Don't apply."),
]
CALL = {"strong": "Apply", "apply": "Apply", "consider": "Consider", "skip": "Skip"}


def band(score: float) -> dict:
    for low, name, letter, fit, label in BANDS:
        if score >= low:
            return {"band": name, "decision": letter, "fitBand": fit, "label": label, "call": CALL[name]}
    raise AssertionError("unreachable")


def _norm(text: str) -> str:
    text = str(text or "").replace("’", "'").replace("‘", "'").replace("“", '"').replace("”", '"').replace("–", "-").replace("—", "-")
    text = "".join(c for c in unicodedata.normalize("NFKD", text) if unicodedata.category(c) != "Mn")
    return re.sub(r"\s+", " ", text).strip().lower()


def verbatim(quote: str, source: str) -> bool:
    """Is `quote` copied from `source`? Whitespace, quote marks, dashes and case are forgiven; words are not.
    A quote may skip text with an ellipsis ("must have ... Python"): each piece must appear, in order."""
    src = _norm(source)
    pos = 0
    for piece in re.split(r"\s*(?:\.\.\.|…)\s*", _norm(quote)):
        piece = piece.strip(" \"'")
        if not piece:
            continue
        i = src.find(piece, pos)
        if i < 0:
            return False
        pos = i + len(piece)
    return bool(_norm(quote).strip(" .\"'…"))


def confidence(ev: dict) -> str:
    """Evidence confidence, by rule (in order): low, then medium, then high."""
    dims = ev.get("dimensions") or {}
    st = {k: (dims.get(k) or {}).get("status", "unknown") for k in DIMENSIONS}
    flags = ev.get("flags") or {}
    unknown = sum(1 for v in st.values() if v == "unknown")
    if flags.get("jdIncomplete") or flags.get("eligibilityUnresolved") or st["cvMatch"] == "unknown" or st["northStar"] == "unknown" or unknown >= 2:
        return "low"
    if any(v != "supported" for v in st.values()) or ev.get("confidenceGaps"):
        return "medium"
    return "high"


def _num(x) -> float | None:
    try:
        return float(x) if not isinstance(x, bool) else None
    except (TypeError, ValueError):
        return None


def validate(ev: dict, jd: str | None = None, brain: dict | None = None) -> tuple[list[str], list[str]]:
    """(errors, warnings). Errors block the evaluation from being saved."""
    errors: list[str] = []
    warnings: list[str] = []
    if not isinstance(ev, dict):
        return ["The evaluation must be a JSON object."], []
    score = _num(ev.get("score"))
    if score is None or not 1.0 <= score <= 5.0 or round(score, 1) != score:
        errors.append("score must be a number from 1.0 to 5.0 with at most one decimal.")
        score = None
    if not str(ev.get("summary", "")).strip():
        errors.append("summary: one sentence giving the reason for the verdict.")
    dims = ev.get("dimensions") if isinstance(ev.get("dimensions"), dict) else {}
    dscores = []
    for k, label in DIMENSIONS.items():
        d = dims.get(k)
        if not isinstance(d, dict):
            errors.append(f"dimensions.{k} ({label}) is missing.")
            continue
        s = d.get("score")
        if not isinstance(s, int) or isinstance(s, bool) or not 1 <= s <= 5:
            errors.append(f"dimensions.{k}.score must be a whole number from 1 to 5.")
        else:
            dscores.append(s)
        if d.get("status") not in STATUSES:
            errors.append(f"dimensions.{k}.status must be one of {', '.join(STATUSES)}.")
        if not str(d.get("note", "")).strip():
            errors.append(f"dimensions.{k}.note: say what the rating rests on.")
        if d.get("status") == "supported" and not str(d.get("source", "")).strip():
            warnings.append(f"dimensions.{k} is 'supported' but names no source.")
    if score is not None and len(dscores) == len(DIMENSIONS) and not min(dscores) <= score <= max(dscores):
        errors.append(f"The overall score {score} sits outside its dimension scores ({min(dscores)}-{max(dscores)}).")
    gaps_q = ev.get("confidenceGaps") or []
    if not isinstance(gaps_q, list) or len(gaps_q) > 3:
        errors.append("confidenceGaps: a list of at most three checks that could change the decision.")
    stated_conf = ev.get("confidence")
    if stated_conf and stated_conf != confidence(ev):
        errors.append(f"confidence is '{stated_conf}' but the evidence rules give '{confidence(ev)}'. Leave it out; it is computed.")

    claims_idx = {}
    if brain:
        from . import brain as brain_mod
        claims_idx = brain_mod.claims(brain)
        for s in brain.get("stories", []) or []:
            if s.get("id"):
                claims_idx.setdefault(s["id"], None)
    reqs = ev.get("requirements") or []
    if not isinstance(reqs, list):
        errors.append("requirements must be a list.")
        reqs = []
    names = set()
    for i, r in enumerate(reqs):
        tag = f"requirements[{i}]"
        if not isinstance(r, dict) or not str(r.get("requirement", "")).strip():
            errors.append(f"{tag}: needs a requirement.")
            continue
        tag = f"Requirement '{r['requirement']}'"
        names.add(_norm(r["requirement"]))
        imp, tier, m = r.get("importance"), r.get("tier"), r.get("match")
        if imp not in IMPORTANCE:
            errors.append(f"{tag}: importance must be one of {', '.join(IMPORTANCE)}.")
        if tier not in TIERS:
            errors.append(f"{tag}: tier must be one of {', '.join(TIERS)}.")
        if m not in MATCHES:
            errors.append(f"{tag}: match must be one of {', '.join(MATCHES)}.")
        if tier == "inferred" and imp in ("critical", "high"):
            errors.append(f"{tag}: an inferred requirement can't be {imp}. Only the posting's own words or structure can make a requirement critical or high.")
        if tier == "stated":
            sig = str(r.get("jdSignal") or "").strip()
            if not sig:
                errors.append(f"{tag}: a stated requirement needs the posting's words in jdSignal.")
            elif jd is not None and not verbatim(sig, jd):
                errors.append(f"{tag}: jdSignal \"{sig[:80]}\" isn't a verbatim quote from the posting.")
        if m == "strong":
            if not str(r.get("evidence", "")).strip():
                errors.append(f"{tag}: a strong match needs evidence from your brain or resume.")
            cid = r.get("claimId")
            if cid and brain is not None:
                if cid not in claims_idx:
                    errors.append(f"{tag}: claimId '{cid}' isn't in the brain.")
                elif claims_idx[cid] is not None and claims_idx[cid].status == "planned":
                    errors.append(f"{tag}: claim '{cid}' is planned work, which can't back a strong match.")
    low_rows = [r for r in reqs if isinstance(r, dict) and r.get("importance") not in ("critical", "high")]
    if len(reqs) > ROW_BUDGET and low_rows:
        errors.append(f"{len(reqs)} requirement rows: keep at most {ROW_BUDGET} (every critical and high row stays; trim meaningful and below, "
                      "unmet before met, and record the number dropped in droppedRequirements).")
    gap_names = {}
    for g in ev.get("gaps") or []:
        if isinstance(g, dict) and g.get("requirement"):
            gap_names[_norm(g["requirement"])] = g
    for r in reqs:
        if isinstance(r, dict) and r.get("importance") in ("critical", "high") and r.get("match") in ("partial", "missing"):
            g = gap_names.get(_norm(r.get("requirement", "")))
            if not g or not str(g.get("risk", "")).strip() or not str(g.get("mitigation", "")).strip():
                errors.append(f"Requirement '{r.get('requirement')}' is {r.get('importance')} and {r.get('match')}: add a gap with the interview risk and a mitigation.")
    co = ev.get("company") or {}
    if co:
        if co.get("type") not in COMPANY_TYPES:
            errors.append(f"company.type must be one of: {'; '.join(COMPANY_TYPES)}.")
        if co.get("compReliability") not in RELIABILITY:
            errors.append("company.compReliability must be high, medium or low.")
        elif co.get("type") == "Unknown" and co.get("compReliability") != "low":
            errors.append("An unknown company type means low pay reliability until evidence improves it.")
    comp = ev.get("comp") or {}
    adv = comp.get("advertised")
    if adv and jd is not None and not verbatim(str(adv), jd):
        errors.append(f"comp.advertised \"{adv}\" must be the posting's own pay text, verbatim (or null when it states none).")
    if score is not None:
        b = band(score)
        dec = ev.get("decision")
        if dec == "A" and score < APPLY_LINE:
            errors.append(f"Decision A (apply now) needs a score of {APPLY_LINE} or more; this one is {score}.")
        if ev.get("answers") and score < APPLY_LINE:
            warnings.append(f"Draft answers are for roles at or above the {APPLY_LINE} apply line; this one is {score}.")
        if b["band"] == "skip" and not ev.get("gaps") and not any((dims.get(k) or {}).get("score", 5) <= 2 for k in DIMENSIONS):
            warnings.append("A skip verdict with no gaps and no low dimension: say what holds the score down.")
    for a in ev.get("answers") or []:
        if not isinstance(a, dict) or not a.get("q") or not a.get("a"):
            errors.append("answers: each needs q and a.")
            break
    if not ev.get("requirements"):
        warnings.append("No requirement rows: the match can't be checked.")
    return errors, warnings


_IMP_RANK = {k: i for i, k in enumerate(IMPORTANCE)}
_MET_RANK = {"missing": 0, "partial": 1, "strong": 2, "na": 3}


def normalize(ev: dict, now: datetime | None = None) -> dict:
    """The evaluation as stored: requirements sorted (importance, then unmet before met), derived fields filled."""
    out = dict(ev)
    out["requirements"] = sorted((r for r in ev.get("requirements") or [] if isinstance(r, dict)),
                                 key=lambda r: (_IMP_RANK.get(r.get("importance"), 9), _MET_RANK.get(r.get("match"), 9)))
    out["score"] = round(float(ev["score"]), 1)
    out["confidence"] = confidence(ev)
    b = band(out["score"])
    out["verdict"] = {"band": b["band"], "call": b["call"], "label": b["label"]}
    out["applyLine"] = APPLY_LINE
    out.setdefault("evaluatedAt", (now or datetime.now(timezone.utc)).strftime("%Y-%m-%dT%H:%M:%SZ"))
    out.pop("decision", None)
    return out


def job_patch(ev: dict, decision: str | None = None) -> dict:
    """The job fields an evaluation sets: the evaluation itself plus the dashboard's
    decision, fit band, reason, evidence map and gap list, so older views still read it."""
    b = band(ev["score"])
    letter = decision if decision in ("A", "B", "C", "D", "E", "F") else b["decision"]
    if letter == "A" and ev["score"] < APPLY_LINE:
        letter = "B"
    evidence = [{"requirement": r["requirement"], "evidence": r.get("evidence", ""), "source": r.get("source", "")}
                for r in ev.get("requirements", []) if r.get("match") in ("strong", "partial") and r.get("evidence")]
    gaps = [f"{g['requirement']}: {g.get('risk', '')}".strip(": ") for g in ev.get("gaps") or [] if isinstance(g, dict) and g.get("requirement")]
    return {"evaluation": ev, "score": ev["score"], "decision": letter, "fitBand": b["fitBand"],
            "decisionReason": ev.get("summary", ""), "evidence": evidence, "gaps": gaps}


def apply_gate(job: dict, chosen_by_user: bool) -> tuple[bool, str]:
    """May auto-apply submit this role? (ok, reason when not).

    Roles you queued or approved without a score may go ahead (you chose them).
    Roles auto-apply picked itself need a score. Any role scored under the apply
    line waits for you to press "Apply anyway" (scoreOverride)."""
    ev = job.get("evaluation") or {}
    s = _num(ev.get("score")) if ev else _num(job.get("score"))
    if s is None:
        return (True, "") if chosen_by_user else (False, "Not scored yet: auto-apply scores a role before applying to it.")
    if s < APPLY_LINE and not job.get("scoreOverride"):
        return False, f"Scored {s:.1f}, under the {APPLY_LINE} apply line. Press Apply anyway if you want it sent."
    return True, ""


# ---------------------------------------------------------------- the report

def _cell(s) -> str:
    return str(s or "").replace("|", "\\|").replace("\n", " ").strip()


def _signal(r: dict) -> str:
    sig = str(r.get("jdSignal") or "").strip()
    if not sig:
        return "—"
    return f"“{sig}”" if r.get("tier") == "stated" else sig  # only stated rows are quotes


def report_md(ev: dict, job: dict | None = None, jd: str | None = None) -> str:
    job = job or {}
    ev = ev if "verdict" in ev else normalize(ev)
    v = ev["verdict"]
    L: list[str] = []
    title, company = job.get("title") or "Role", job.get("company") or ""
    L.append(f"# {title}{' at ' + company if company else ''}")
    L.append("")
    L.append(f"**Score:** {ev['score']:.1f}/5 · **Decision:** {v['call']} · **Confidence:** {ev['confidence'].title()}")
    if job.get("url"):
        L.append(f"**Posting:** {job['url']}")
    L.append(f"**Evaluated:** {ev.get('evaluatedAt', '')[:10]}{' · ' + ev['archetype'] if ev.get('archetype') else ''}")
    L += ["", "## Verdict (lead)", "", f"**{v['call']}.** {ev.get('summary', '')}", "",
          f"_{v['label']} The apply line is {APPLY_LINE}: below it CareerOS recommends against applying, and auto-apply waits for you._", ""]

    facts = job.get("facts") or {}
    rows = [("Company", company), ("Role", job.get("title")), ("Role family", ev.get("archetype") or job.get("archetype")),
            ("Location", job.get("location")), ("Work mode", job.get("workMode")), ("Experience asked", job.get("experience")),
            ("Pay shown", job.get("salary") or (ev.get("comp") or {}).get("advertised")), ("Posted", (job.get("postedAt") or "")[:10])]
    rows = [(k, val) for k, val in rows if val]
    if rows:
        L += ["## A) Role summary", "", "| | |", "|---|---|"] + [f"| {k} | {_cell(val)} |" for k, val in rows] + [""]

    reqs = ev.get("requirements") or []
    if reqs:
        L += ["## B) Match with your experience", "", "| Requirement | Importance | Match | Posting says | Evidence / gap |", "|---|---|---|---|---|"]
        for r in reqs:
            L.append(f"| {_cell(r['requirement'])} | {r.get('importance', '').replace('_', ' ')} ({r.get('tier', '')}) | {MATCH_LABEL.get(r.get('match'), '')} "
                     f"| {_cell(_signal(r))} | {_cell(r.get('evidence') or r.get('gap') or '')} |")
        if ev.get("droppedRequirements"):
            L.append(f"\n+{ev['droppedRequirements']} lower-importance requirements not listed.")
        L.append("")
    gaps = [g for g in ev.get("gaps") or [] if isinstance(g, dict)]
    if gaps:
        L += ["### Gaps", ""]
        for g in gaps:
            L.append(f"- **{g.get('requirement')}** ({'hard blocker' if g.get('blocker') else 'not a blocker'}). "
                     f"Interview risk: {g.get('risk', '')} Mitigation: {g.get('mitigation', '')}")
        L.append("")
    lv = ev.get("level") or {}
    if lv:
        L += ["## C) Level and strategy", ""]
        for k, lab in (("detected", "Level in the posting"), ("yours", "Your natural level"), ("pitch", "How to pitch it truthfully"),
                       ("ifDownleveled", "If they offer a lower level")):
            if lv.get(k):
                L.append(f"- **{lab}:** {lv[k]}")
        L.append("")
    co, comp = ev.get("company") or {}, ev.get("comp") or {}
    if co or comp:
        L += ["## D) Pay and company type", ""]
        if co.get("type"):
            L.append(f"- **Company type:** {co['type']} (pay figures for this type are {co.get('compReliability', 'low')}-reliability){'. ' + co['note'] if co.get('note') else ''}")
        L.append(f"- **Posting's pay:** {comp.get('advertised') or 'not stated'}")
        if comp.get("market"):
            L.append(f"- **Market:** {comp['market']}")
        for s in comp.get("sources") or []:
            L.append(f"  - [{s.get('title', s.get('url'))}]({s.get('url')})" if isinstance(s, dict) else f"  - {s}")
        L.append("")
    if ev.get("customization"):
        L += ["## E) Resume changes for this role", "", "| # | Section | Change | Why |", "|---|---|---|---|"]
        L += [f"| {i} | {_cell(c.get('section'))} | {_cell(c.get('change'))} | {_cell(c.get('why'))} |" for i, c in enumerate(ev["customization"], 1)]
        L.append("")
    if ev.get("interviewPlan"):
        L += ["## F) Interview plan", "", "| Requirement | Your story | From |", "|---|---|---|"]
        L += [f"| {_cell(s.get('requirement'))} | {_cell(s.get('story'))} | {_cell(s.get('claimId'))} |" for s in ev["interviewPlan"]]
        L.append("")
    lg = job.get("legitimacy") or facts.get("legit") or {}
    if lg:
        L += ["## G) Is the posting real?", "", f"**{lg.get('label', '')}.** These are observations, not accusations.", ""]
        for s in lg.get("signals") or []:
            L.append(f"- {s.get('signal')}: {s.get('note')}{' “' + s['quote'] + '”' if s.get('quote') else ''}")
        L.append("")
    L += ["## Risk summary", "", "| Signal | Status |", "|---|---|"]
    L.append(f"| Posting legitimacy | {('✅ ' if lg.get('tier') == 'high' else '⚠️ ') + lg.get('label', '') if lg else '— not evaluated'} |")
    wa = facts.get("workAuth") or {}
    L.append(f"| Work authorization | {'⚠️ “' + _cell(wa.get('quote')) + '”' if wa else '✅ no restriction stated'} |")
    rp = job.get("reposts") or facts.get("reposts") or {}
    L.append(f"| Re-listed | {'⚠️ ' + str(rp['count']) + '× since ' + str(rp.get('since', '')) if rp.get('count') else '✅ not seen before'} |")
    L.append(f"| Recruiter posting | {'⚠️ “' + _cell(facts['agencyQuote']) + '”' if facts.get('agencyQuote') else '✅ employer named'} |")
    L += ["", "## Score evidence", "", "| Dimension | Score | Evidence | Based on |", "|---|---|---|---|"]
    for k, lab in DIMENSIONS.items():
        d = (ev.get("dimensions") or {}).get(k) or {}
        L.append(f"| {lab} | {d.get('score', '')} | {d.get('status', '')} | {_cell(d.get('note'))}{' (' + _cell(d['source']) + ')' if d.get('source') else ''} |")
    L += ["", f"**Confidence: {ev['confidence'].title()}.** This rates the evidence behind the score, not your chance of an interview."]
    if ev.get("confidenceGaps"):
        L.append("Checks that could change this: " + "; ".join(ev["confidenceGaps"]) + ".")
    L.append("")
    if ev.get("answers"):
        L += ["## H) Draft application answers", ""]
        for a in ev["answers"]:
            L += [f"**{a['q']}**", "", a["a"], ""]
    if ev.get("keywords"):
        L += ["## Keywords from the posting", "", ", ".join(ev["keywords"]), ""]
    if jd:
        L += ["## Job description (archived verbatim)", "", f"Posted: {(job.get('postedAt') or '')[:10] or 'not visible in source'}", "", jd.strip(), ""]
    return "\n".join(L).rstrip() + "\n"
