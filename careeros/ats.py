"""How an applicant-tracking system reads your resume PDF, and what to fix.

    careeros ats-check resume.pdf --applicant applicant.json --terms market.json

ATS parsers read the PDF's text layer top to bottom, look for standard section
headings, pull contact details and dates, and recruiters then search the parsed
text for keywords. Each check below is one of those steps; the score is the
weighted share that passes. It never rewrites the resume: fixes that add a
skill are for skills you really have (`careeros market` says which ones roles
ask for).
"""

from __future__ import annotations

import re
from pathlib import Path

HEADINGS = {
    "experience": r"(professional |work )?experience|employment( history)?",
    "education": r"education|academic",
    "skills": r"(core |technical )?skills",
    "projects": r"projects|selected projects|ai-native products",
}
_MONTH = r"(jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)[a-z]*\.?"
_FULL = re.compile(rf"\b{_MONTH}\s+(19|20)\d\d\s*[–—-]\s*({_MONTH}\s+(19|20)\d\d|present|current|now)\b", re.I)
_RANGE = re.compile(rf"\b({_MONTH}\s+)?(19|20)\d\d\s*[–—-]\s*({_MONTH}\s+)?((19|20)\d\d|present|current|now)\b", re.I)


def pdf_text(path: str | Path) -> tuple[str, int]:
    from pypdf import PdfReader  # in the cloud extra; render.py already relies on it
    r = PdfReader(str(path))
    return "\n".join(p.extract_text() or "" for p in r.pages), len(r.pages)


def _has(term: str, text: str) -> bool:
    t = re.escape(term.lower()).replace(r"\ ", r"[\s-]*")
    return bool(re.search(rf"(?<![a-z0-9]){t}(?![a-z0-9])", text.lower()))


def check(text: str, pages: int, filename: str = "", profile: dict | None = None, terms: list[str] | None = None) -> dict:
    profile = profile or {}
    low = text.lower()
    words = len(re.findall(r"\w+", text))
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    checks: list[dict] = []

    def add(cid, ok, weight, title, fix):
        checks.append({"id": cid, "ok": bool(ok), "weight": weight, "title": title, "fix": fix})

    add("text", words >= 150, 20, "The PDF has a real text layer",
        "Export the resume as a text PDF (not a scan or image); an ATS reads an image as an empty resume.")
    email = re.search(r"[\w.+-]+@[\w-]+\.[\w.]+", text)
    phone = re.search(r"(\+?\d[\d\s-]{8,}\d)", text)
    add("contact", email and phone, 10, "Email and phone are readable",
        "Put your email and phone as plain text in the first lines (not in a header image or icon-only).")
    head = "\n".join(lines[:4]).lower()
    add("links", "linkedin.com/" in low and "github.com/" in low, 5, "LinkedIn and GitHub links are present",
        "Add linkedin.com/in/... and github.com/... as plain text; recruiters open both.")
    name = (profile.get("fullName") or "").strip()
    add("name", not name or name.lower().split()[0] in head, 5, "Your name is the first thing on the page",
        "Start the resume with your full name on its own line.")
    missing = [h for h, rx in HEADINGS.items() if not re.search(rf"^\s*({rx})\s*$", text, re.I | re.M)]
    add("headings", not missing, 10, "Standard section headings (Experience, Education, Skills, Projects)",
        "Use plain headings an ATS knows" + (f"; missing: {', '.join(missing)}." if missing else "."))
    years = float(profile.get("experienceYears") or 0)
    add("length", pages <= 1 or years >= 3, 10, "One page for under 3 years of experience",
        f"Cut to one page: it is {pages} pages. Keep the 3 strongest projects, shorten the summary to 2 lines "
        "and move the long skills list into one line per group.")
    ranges = len(_RANGE.findall(text))
    full = len(_FULL.findall(text))
    add("dates", ranges and full == ranges, 10, "Every role has month-and-year dates",
        "Write dates as 'Nov 2023 – Mar 2025' on every role; a year without a month (or a missing date) "
        "makes parsers guess your experience.")
    bullets = [l for l in lines if len(l.split()) >= 8 and not l.isupper()]
    quantified = [l for l in bullets if re.search(r"\d", l)]
    share = len(quantified) / len(bullets) if bullets else 0
    add("numbers", share >= 0.35, 10, f"Results with numbers ({share:.0%} of lines)",
        "Give more bullets a number you can defend: users, latency, tests, cost, time saved, roles scanned.")
    summary = re.search(r"(professional )?summary\s*\n(.+?)\n\s*(core skills|skills|experience)", text, re.I | re.S)
    sw = len(summary.group(2).split()) if summary else 0
    add("summary", sw <= 60, 5, f"A short summary ({sw} words)" if summary else "Summary length",
        "Keep the summary to 2 lines (under 60 words): target role, strongest proof, stack.")
    fn = Path(filename).name.lower() if filename else ""
    first = name.lower().split()[0] if name else ""
    add("filename", not fn or (("resume" in fn or "cv" in fn) and (not first or first in fn)), 5,
        "File name says who and what", "Name the file '<Full Name> - Resume.pdf'; random ids look careless in a recruiter's inbox.")
    cov = None
    if terms:
        have = [t for t in terms if _has(t, text)]
        cov = len(have) / len(terms)
        miss = [t for t in terms if t not in have]
        add("keywords", cov >= 0.6, 10, f"Covers {cov:.0%} of the skills these roles ask for most",
            "Add the ones you really use to Skills and to a bullet that shows them: " + ", ".join(miss[:8]) + ".")
    total = sum(c["weight"] for c in checks)
    score = round(100 * sum(c["weight"] for c in checks if c["ok"]) / total) if total else 0
    return {"score": score, "pages": pages, "words": words, "keywordCoverage": cov, "checks": checks}


def check_file(path: str | Path, profile: dict | None = None, terms: list[str] | None = None) -> dict:
    text, pages = pdf_text(path) if str(path).lower().endswith(".pdf") else (Path(path).read_text(encoding="utf-8"), 1)
    name = (profile or {}).get("resume", {}).get("name") if isinstance((profile or {}).get("resume"), dict) else ""
    return check(text, pages, name or str(path), profile, terms)
