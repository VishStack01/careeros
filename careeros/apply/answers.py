"""Resolve application-form fields to answers, with a confidence for each.

The rule that keeps auto-apply safe: an application goes out on its own only
when every required field is answered from your profile, your brain, or a
per-job package you (or the Reviewer) approved. Anything else is escalated to
you with the exact question, instead of being guessed.

Confidence levels
  high      copied from the profile or package (your words)
  medium    derived: years of a skill from the brain, a fuzzy option match,
            a reworded question matched to a reviewed package answer
  escalate  needs you: sensitive data, essays nobody wrote yet, unclear legal questions
  skip      optional field with no good answer; left blank
"""

from __future__ import annotations

import re
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

from .. import brain as brain_mod
from ..textutil import norm

HIGH, MEDIUM, ESCALATE, SKIP = "high", "medium", "escalate", "skip"

_DECLINE = re.compile(r"decline|prefer not|don.?t wish|do not wish|not to (say|disclose|answer|self)|rather not|i don.?t want", re.I)
_YES = re.compile(r"^(yes|y|true|i do|i am|i will|i have|i can|agree|i agree)\b", re.I)
_NO = re.compile(r"^(no|n|false|i don.?t|i do not|i am not|i will not|i won.?t|i cannot|i can.?t)\b", re.I)
_NEVER_AUTOFILL = re.compile(
    r"aadha?a?r|\bpan\b|passport|social security|\bssn\b|bank account|ifsc|date of birth|\bdob\b|"
    r"password|credit card|national id|tax id|driver.?s licen",
    re.I,
)
_COUNTRIES = {
    "india": "India", "united states": "United States", "usa": "United States", "u.s.": "United States", " us ": "United States",
    "united kingdom": "United Kingdom", " uk ": "United Kingdom", "canada": "Canada", "germany": "Germany",
    "european union": "European Union", " eu ": "European Union", "singapore": "Singapore", "australia": "Australia",
    "netherlands": "Netherlands", "ireland": "Ireland", "uae": "United Arab Emirates",
}


@dataclass
class Field:
    key: str
    label: str
    type: str = "text"  # text email tel url number textarea select radio checkbox file date
    required: bool = False
    options: list[str] = field(default_factory=list)
    name: str = ""


@dataclass
class Resolution:
    field: Field
    value: object
    confidence: str
    source: str
    reason: str = ""

    def to_dict(self) -> dict:
        return {"label": self.field.label, "type": self.field.type, "required": self.field.required,
                "value": self.value, "confidence": self.confidence, "source": self.source, "reason": self.reason}


@dataclass
class Context:
    profile: dict
    brain: dict = field(default_factory=dict)
    package: dict = field(default_factory=dict)  # {"resume": path, "cover_note": str, "answers": {question: answer}}
    job: dict = field(default_factory=dict)

    @classmethod
    def load(cls, profile_path, brain_path=None, package: dict | None = None, job: dict | None = None) -> "Context":
        profile = tomllib.loads(Path(profile_path).read_text(encoding="utf-8"))
        b = brain_mod.load(brain_path) if brain_path and Path(brain_path).exists() else {}
        return cls(profile, b, package or {}, job or {})

    def p(self, dotted: str, default=None):
        cur = self.profile
        for part in dotted.split("."):
            if not isinstance(cur, dict) or part not in cur:
                return default
            cur = cur[part]
        return cur


# ------------------------------------------------------------------ option matching

def _ranges(option: str) -> tuple[float, float] | None:
    o = option.lower()
    if re.search(r"immediate|right away|currently serving|(?<!\d)0 ?days", o):
        return (0, 0)
    nums = [float(n) for n in re.findall(r"\d+(?:\.\d+)?", o)]
    if not nums:
        return None
    if re.search(r"less than|under|below|up to|<|or less|or fewer", o):
        return (0, nums[0] - (0 if re.search(r"up to|or less|or fewer", o) else 1e-9))
    if re.search(r"\+|more than|over|above|or more|>", o):
        return (nums[0] + (1e-9 if re.search(r"more than|over|above|>", o) else 0), float("inf"))
    if len(nums) >= 2:
        return (nums[0], nums[1])
    return (nums[0], nums[0])


def match_option(value, options: list[str]) -> tuple[str | None, str]:
    """Pick the option that says the same thing as `value`. Returns (option, confidence)."""
    if not options:
        return None, ESCALATE
    opts = [o for o in options if o and not re.fullmatch(r"(select|choose|please select|--+).*", o.strip(), re.I)]
    if isinstance(value, bool):
        rx = _YES if value else _NO
        hit = next((o for o in opts if rx.search(o.strip())), None)
        return (hit, HIGH) if hit else (None, ESCALATE)
    if value == "__decline__":
        hit = next((o for o in opts if _DECLINE.search(o)), None)
        return (hit, HIGH) if hit else (None, ESCALATE)
    if isinstance(value, (int, float)):
        for o in opts:
            r = _ranges(o)
            if r and r[0] <= value <= r[1]:
                return o, MEDIUM
        return None, ESCALATE
    v = norm(str(value))
    for o in opts:
        if norm(o) == v:
            return o, HIGH
    for o in opts:
        no = norm(o)
        if no and (no.startswith(v) or v.startswith(no)):
            return o, MEDIUM
    for o in opts:
        no = norm(o)
        if no and (v in no or no in v):
            return o, MEDIUM
    return None, ESCALATE


# ------------------------------------------------------------------ the rules

def _country_in(label: str) -> str | None:
    padded = f" {label.lower()} "
    for k, v in _COUNTRIES.items():
        if k in padded:
            return v
    return None


def _years_total(ctx: Context) -> float | None:
    months = ctx.p("work.total_experience_months")
    return None if months is None else round(months / 12, 1)


def _rule_based(f: Field, ctx: Context):
    """Return (value, confidence, source) or None if no rule applies."""
    L = f.label.lower()

    if _NEVER_AUTOFILL.search(L):
        return (None, ESCALATE, "sensitive: you enter this yourself")

    # Diversity / EEO questions: decline unless the profile says otherwise.
    if re.search(r"gender|pronoun|race|ethnic|veteran|disabilit|sexual orientation|transgender|hispanic|latin", L):
        key = next((k for k in ("gender", "race", "veteran", "disability") if k in L), "gender")
        v = ctx.p(f"eeo.{key}", "decline")
        return ("__decline__" if v == "decline" else v, HIGH, f"profile eeo.{key}")

    if f.type == "file":
        if re.search(r"resume|cv|curriculum", L):
            r = ctx.package.get("resume")
            return (r, HIGH, "package resume") if r else (None, ESCALATE, "no tailored resume in the package")
        if re.search(r"cover", L):
            c = ctx.package.get("cover_letter_file")
            return (c, HIGH, "package cover letter") if c else None
        return None

    if re.search(r"(12th|class ?12|xii|higher secondary)", L):
        return (ctx.p("education.class12"), HIGH, "profile education.class12")
    if re.search(r"(10th|class ?10|\bx\b|secondary school|sslc)", L):
        return (ctx.p("education.class10"), HIGH, "profile education.class10")

    simple = [] if f.type == "checkbox" else [
        (r"\bfirst name\b|\bgiven name\b", "identity.first_name"),
        (r"\blast name\b|\bsurname\b|\bfamily name\b", "identity.last_name"),
        (r"^\s*(full |legal |your )?name\s*\*?\s*$|\bfull name\b", "identity.full_name"),
        (r"e-?mail", "identity.email"),
        (r"phone|mobile|contact number|whatsapp", "identity.phone"),
        (r"linkedin", "identity.linkedin"),
        (r"github", "identity.github"),
        (r"portfolio|personal (site|website)|^website|website url", "identity.portfolio"),
        (r"current (company|employer|organi[sz]ation)", "work.current_company"),
        (r"current (job )?(title|designation|role)", "work.current_title"),
        (r"college|university|institution|school name", "education.college"),
        (r"degree|highest (level of )?education|qualification", "education.degree"),
        (r"branch|major|field of study|specialization|stream", "education.branch"),
        (r"cgpa|\bgpa\b|aggregate|percentage|marks", "education.cgpa"),
        (r"how did you (hear|find|learn)|where did you (hear|find)|^source\b", "answers.how_heard"),
        (r"earliest (start|joining)|when can you (start|join)|availability to start|start date", "work.earliest_start"),
    ]
    for rx, key in simple:
        if re.search(rx, L):
            v = ctx.p(key)
            return (v, HIGH, f"profile {key}") if v not in (None, "") else (None, ESCALATE, f"profile {key} is empty")

    if re.search(r"graduat|year of passing|passing year|batch", L):
        return (ctx.p("education.graduation_year"), HIGH, "profile education.graduation_year")
    if re.search(r"backlog", L):
        return (bool(ctx.p("education.backlogs", False)), HIGH, "profile education.backlogs")

    if re.search(r"(current|present|city|where).*(locat|based|live|reside)|^\s*(current )?(location|city)\b", L):
        parts = [ctx.p("identity.city"), ctx.p("identity.state"), ctx.p("identity.country")]
        return (", ".join(p for p in parts if p), HIGH, "profile identity.city/state/country")

    if re.search(r"(current|present).*(ctc|salary|compensation|pay)", L):
        v = ctx.p("work.current_ctc_lpa")
        return (f"{v} LPA" if f.type not in ("number",) else v, HIGH, "profile work.current_ctc_lpa") if v is not None else (None, ESCALATE, "current CTC not in profile")
    if re.search(r"expected.*(ctc|salary|compensation|pay)|salary expectation|desired (salary|compensation)", L):
        v = ctx.p("work.expected_ctc_lpa")
        return (f"{v} LPA" if f.type not in ("number",) else v, HIGH, "profile work.expected_ctc_lpa") if v is not None else (None, ESCALATE, "expected CTC not in profile")
    if re.search(r"notice period", L):
        v = ctx.p("work.notice_days")
        if v is None:
            return (None, ESCALATE, "notice period not in profile")
        return (v if f.type in ("select", "radio", "number") else f"{v} days", HIGH, "profile work.notice_days")

    if re.search(r"sponsor|visa", L):
        return (bool(ctx.p("terms.needs_sponsorship", False)), HIGH, "profile terms.needs_sponsorship")
    if re.search(r"(legally )?(authori[sz]ed|eligible|right) to work", L):
        allowed = [c.lower() for c in ctx.p("terms.work_authorization", [])]
        country = _country_in(L)
        if country:
            return (country.lower() in allowed, HIGH, "profile terms.work_authorization")
        job_loc = (ctx.job.get("location", "") + " " + ctx.job.get("region", "")).lower()
        if "india" in job_loc or ctx.job.get("region") in ("south-india", "remote-india"):
            return ("india" in allowed, HIGH, "profile terms.work_authorization (role is in India)")
        return (None, ESCALATE, "the question doesn't name a country and the role isn't in India")
    if re.search(r"relocat", L):
        willing = bool(ctx.p("terms.relocate_within"))
        return (willing, MEDIUM, "profile terms.relocate_within")
    if re.search(r"(us|est|pst|pacific|eastern|overlap|night|shift).*(hours|time ?zone|shift)|work in .* time ?zone", L):
        v = ctx.p("terms.us_hours", "no")
        if v == "partly":
            return (None, ESCALATE, "profile says 'partly' for US hours; you decide per role")
        return (v == "yes", HIGH, "profile terms.us_hours")
    if re.search(r"internship", L) and re.search(r"open|willing|ok|interested", L):
        return (bool(ctx.p("terms.open_to_internships", False)), HIGH, "profile terms.open_to_internships")
    if re.search(r"language", L):
        return (", ".join(ctx.p("terms.languages", [])), HIGH, "profile terms.languages")

    m = re.search(r"(?:years?|how long)\b[^?]*?\b(?:with|in|using|of) ((?!experience\b)[a-z0-9+#./-]+(?: [a-z0-9+#./-]+){0,2})\s*\??\s*\*?$", L) \
        or re.search(r"years? of (?:professional |relevant |work |hands[- ]on |total )?experience", L)
    if m:
        skill = (m.group(1) or "").strip(" ?*.") if m.lastindex else ""
        if re.fullmatch(r"(professional |relevant |work |total )?experience|the (industry|field)|industry", skill):
            skill = ""
        if skill:
            yrs = brain_mod.skill_years(ctx.brain, skill) if ctx.brain else None
            if yrs is None:
                return (None, ESCALATE, f"no '{skill}' entry with years in your brain")
            conf = MEDIUM if ctx.p("policy.allow_inferred_answers", True) else ESCALATE
            return (yrs if f.type in ("number", "select", "radio") else f"{yrs:g}", conf, f"brain skill '{skill}'")
        yrs = _years_total(ctx)
        if yrs is None:
            return (None, ESCALATE, "total experience not in profile")
        return (yrs if f.type in ("number", "select", "radio") else f"{yrs:g}", HIGH, "profile work.total_experience_months")

    if re.search(r"currently employed|are you (currently )?working", L):
        return (ctx.p("work.status") == "working", HIGH, "profile work.status")

    if f.type == "checkbox" and re.search(r"privacy|consent|data (processing|protection)|acknowledg|i (agree|confirm|understand|certify)|terms", L):
        if ctx.p("policy.auto_acknowledge_privacy_notice", False):
            return (True, MEDIUM, "policy auto_acknowledge_privacy_notice")
        return (None, ESCALATE, "acknowledgement checkbox: you tick this yourself unless you allow it in policy")

    if re.search(r"cover (letter|note)|additional information|anything else", L) and f.type in ("textarea", "text"):
        note = ctx.package.get("cover_note")
        if note:
            return (note, HIGH, "package cover note")
    return None


def _package_answer(f: Field, ctx: Context):
    answers = ctx.package.get("answers") or {}
    if not answers:
        return None
    q = norm(f.label)
    for k, v in answers.items():
        if norm(k) == q:
            return (v, HIGH, "package answer (exact question)")
    qt = set(q.split())
    best, score = None, 0.0
    for k, v in answers.items():
        kt = set(norm(k).split())
        if not kt or not qt:
            continue
        s = len(qt & kt) / len(qt | kt)
        if s > score:
            best, score = (k, v), s
    if best and score >= 0.6:
        return (best[1], MEDIUM, f"package answer for '{best[0]}' (similar question)")
    return None


def resolve(f: Field, ctx: Context) -> Resolution:
    hit = _rule_based(f, ctx) or _package_answer(f, ctx)
    if hit is None:
        if f.required:
            kind = "an essay question nobody has answered yet" if f.type == "textarea" else "a question the profile doesn't cover"
            return Resolution(f, None, ESCALATE, "none", f"Required: {kind}.")
        return Resolution(f, None, SKIP, "none", "Optional and not covered; left blank.")
    value, conf, source = hit
    if conf == ESCALATE:
        return Resolution(f, None, ESCALATE if f.required or _NEVER_AUTOFILL.search(f.label) else SKIP, source, source)
    if f.type in ("select", "radio") and f.options:
        opt, oconf = match_option(value, f.options)
        if opt is None:
            return Resolution(f, None, ESCALATE if f.required else SKIP, source, f"No option matches '{value}'.")
        conf = MEDIUM if MEDIUM in (conf, oconf) else conf
        return Resolution(f, opt, conf, source)
    if f.type == "checkbox":
        return Resolution(f, bool(value), conf, source)
    if value == "__decline__":
        value = "Prefer not to say"
    return Resolution(f, value, conf, source)


def resolve_all(fields: list[Field], ctx: Context) -> list[Resolution]:
    return [resolve(f, ctx) for f in fields]


def ready_to_submit(resolutions: list[Resolution], allow_medium: bool = True) -> tuple[bool, list[str]]:
    """Can this go out without a human? Returns (ok, reasons it can't)."""
    reasons = []
    for r in resolutions:
        if r.confidence == ESCALATE and r.field.required:
            reasons.append(f"'{r.field.label}': {r.reason or 'needs you'}")
        elif r.confidence == ESCALATE and _NEVER_AUTOFILL.search(r.field.label):
            reasons.append(f"'{r.field.label}': sensitive field, you fill it yourself")
        elif r.confidence == MEDIUM and not allow_medium and r.field.required:
            reasons.append(f"'{r.field.label}': inferred answer ({r.source}) needs a look")
    return (not reasons, reasons)
