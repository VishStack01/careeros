"""Render a checked resume.json (and a cover note) to an ATS-safe PDF.

    careeros render packages/<id>/resume.json --brain brain/brain.json --profile applicant.json --out resume.pdf
    careeros render --cover packages/<id>/cover.txt --brain brain/brain.json --company "Acme" --out cover.pdf

The layout is what applicant-tracking systems parse cleanly: one column,
standard headings (Summary, Skills, Experience, Projects, Education), real text
(no images, icons, tables or columns), reverse-chronological roles, and links
written out. Every bullet comes from resume.json, which `careeros claims-check`
has already traced to the brain; dates, employers and project names come from
the brain itself, so the renderer adds no facts of its own. After rendering, the
PDF's text is checked again (`claims.check_pdf`).

Turning HTML into PDF needs Playwright's Chromium (pip install "careeros[browser]").
"""

from __future__ import annotations

import html
import re
from datetime import datetime
from pathlib import Path

from .brain import claims as brain_claims

CSS = """
@page{size:A4;margin:13mm 15mm}
*{box-sizing:border-box}
body{margin:0;font-family:Arial,"Liberation Sans",Helvetica,sans-serif;font-size:10.2pt;line-height:1.38;color:#111}
h1{font-size:19pt;margin:0 0 2pt;letter-spacing:-.2pt}
.headline{font-size:11pt;margin:0 0 3pt;color:#222}
.contact{font-size:9.4pt;color:#333;margin:0 0 8pt}
.contact a{color:#333;text-decoration:none}
h2{font-size:10.6pt;text-transform:uppercase;letter-spacing:.6pt;border-bottom:1px solid #999;padding-bottom:2pt;margin:10pt 0 5pt}
p{margin:0 0 4pt}
.role{margin:0 0 6pt;break-inside:avoid}
.rh{display:flex;justify-content:space-between;gap:12pt;font-weight:bold}
.rh .when{font-weight:normal;color:#333;white-space:nowrap}
.sub{color:#333;font-style:italic;margin:0 0 2pt}
ul{margin:2pt 0 0;padding-left:14pt}
li{margin:0 0 2pt}
.letter p{margin:0 0 9pt;font-size:10.8pt;line-height:1.5}
"""

_MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


def _e(s) -> str:
    return html.escape(str(s or ""), quote=True)


def _date(s: str) -> str:
    s = str(s or "").strip()
    m = re.fullmatch(r"(\d{4})-(\d{1,2})(?:-\d{1,2})?", s)
    if m:
        return f"{_MONTHS[int(m.group(2)) - 1]} {m.group(1)}"
    return s


def _span(start, end, status="") -> str:
    a = _date(start)
    b = "Present" if (not end and (status or "").lower() in ("current", "in_progress", "")) else _date(end)
    return f"{a} – {b}" if a and b else a or b


def _contact(brain: dict, profile: dict | None) -> list[str]:
    ident, prof = brain.get("identity") or {}, profile or {}
    items = [prof.get("city") or ident.get("location"), prof.get("email") or ident.get("email"), prof.get("phone") or ident.get("phone")]
    links = dict(ident.get("links") or {})
    for k in ("linkedin", "github", "portfolio"):
        if prof.get(k):
            links[k] = prof[k]
    out = [_e(x) for x in items if x]
    for _, url in links.items():
        if url:
            shown = re.sub(r"^https?://(www\.)?", "", str(url)).rstrip("/")
            out.append(f'<a href="{_e(url)}">{_e(shown)}</a>')
    return out


def resume_html(resume: dict, brain: dict, profile: dict | None = None) -> str:
    """The resume as one self-contained HTML page. Bullets are grouped under the
    role or project their first brain reference belongs to, in resume order."""
    ident = brain.get("identity") or {}
    name = (profile or {}).get("fullName") or ident.get("name", "")
    idx = brain_claims(brain)
    exp_by_org = {e.get("org", ""): e for e in brain.get("experience", [])}
    proj_by_name = {p.get("name", ""): p for p in brain.get("projects", [])}
    groups: dict[tuple[str, str], list[str]] = {}
    loose: list[str] = []
    for b in resume.get("bullets", []):
        refs = [r for r in (b.get("refs") or []) if r in idx]
        if not refs:
            loose.append(b.get("text", ""))
            continue
        c = idx[refs[0]]
        groups.setdefault((c.kind, c.parent), []).append(b.get("text", ""))

    def sort_start(org):
        return str(exp_by_org.get(org, {}).get("start") or "")
    L = ["<!doctype html><html lang=\"en\"><head><meta charset=\"utf-8\">",
         f"<title>{_e(name)} - Resume</title><style>{CSS}</style></head><body>",
         f"<h1>{_e(name)}</h1>"]
    headline = resume.get("headline") or ident.get("headline")
    if headline:
        L.append(f'<p class="headline">{_e(headline)}</p>')
    L.append(f'<p class="contact">{" · ".join(_contact(brain, profile))}</p>')
    if resume.get("summary"):
        L += ["<h2>Summary</h2>", f"<p>{_e(resume['summary'])}</p>"]
    if resume.get("skills"):
        L += ["<h2>Skills</h2>", f"<p>{_e(', '.join(resume['skills']))}</p>"]
    exp = sorted((p for k, p in groups if k == "experience"), key=sort_start, reverse=True)
    if exp:
        L.append("<h2>Experience</h2>")
        for org in exp:
            e = exp_by_org.get(org, {})
            L.append(f'<div class="role"><div class="rh"><span>{_e(e.get("title", ""))}{", " if e.get("title") else ""}{_e(org)}</span>'
                     f'<span class="when">{_e(_span(e.get("start"), e.get("end"), e.get("status")))}</span></div>'
                     + (f'<p class="sub">{_e(e.get("location"))}</p>' if e.get("location") else "")
                     + "<ul>" + "".join(f"<li>{_e(t)}</li>" for t in groups[("experience", org)]) + "</ul></div>")
    projs = [p for k, p in groups if k == "project"]
    if projs:
        L.append("<h2>Projects</h2>")
        for pname in projs:
            p = proj_by_name.get(pname, {})
            note = p.get("builtWith")
            link = p.get("url") or ""
            L.append(f'<div class="role"><div class="rh"><span>{_e(pname)}{" (built with " + _e(note) + ")" if note else ""}</span>'
                     f'<span class="when">{_e(_span(p.get("start"), p.get("end"), p.get("status")) if p.get("start") else "")}</span></div>'
                     + (f'<p class="sub"><a href="{_e(link)}">{_e(re.sub(r"^https?://", "", link))}</a></p>' if link else "")
                     + "<ul>" + "".join(f"<li>{_e(t)}</li>" for t in groups[("project", pname)]) + "</ul></div>")
    if loose:
        L += ["<h2>Highlights</h2>", "<ul>" + "".join(f"<li>{_e(t)}</li>" for t in loose) + "</ul>"]
    edu = resume.get("education") or brain.get("education") or []
    if edu:
        L.append("<h2>Education</h2>")
        for ed in edu:
            deg = ", ".join(x for x in (ed.get("degree"), ed.get("field")) if x)
            grade = ed.get("grade") or ed.get("score")
            L.append(f'<div class="role"><div class="rh"><span>{_e(deg)}{" · " + _e(ed.get("school")) if ed.get("school") else ""}</span>'
                     f'<span class="when">{_e(_span(ed.get("start"), ed.get("end"), "past"))}</span></div>'
                     + (f'<p class="sub">{_e(grade)}</p>' if grade else "") + "</div>")
    L.append("</body></html>")
    return "\n".join(L)


def cover_html(text: str, brain: dict, profile: dict | None = None, company: str = "", date: str = "") -> str:
    ident = brain.get("identity") or {}
    name = (profile or {}).get("fullName") or ident.get("name", "")
    paras = [p.strip() for p in re.split(r"\n\s*\n", text or "") if p.strip()]
    date = date or datetime.now().strftime("%d %B %Y").lstrip("0")
    return ("<!doctype html><html lang=\"en\"><head><meta charset=\"utf-8\">"
            f"<title>{_e(name)} - Cover letter</title><style>{CSS}</style></head><body class=\"letter\">"
            f"<h1>{_e(name)}</h1><p class=\"contact\">{' · '.join(_contact(brain, profile))}</p>"
            f"<p>{_e(date)}</p>" + (f"<p>{_e(company)}</p>" if company else "")
            + "".join(f"<p>{_e(p)}</p>" for p in paras) + f"<p>{_e(name)}</p></body></html>")


def to_pdf(page_html: str, out: str | Path) -> Path:
    """Print HTML to PDF with Playwright's Chromium."""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as e:  # pragma: no cover
        raise RuntimeError('Rendering a PDF needs Playwright: pip install "careeros[browser]"') from e
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as p:
        b = p.chromium.launch()
        try:
            pg = b.new_page()
            pg.set_content(page_html, wait_until="load")
            pg.pdf(path=str(out), format="A4", print_background=True, prefer_css_page_size=True)
        finally:
            b.close()
    return out


def pdf_text(path: str | Path) -> str:
    """The text an applicant-tracking system would read from the PDF."""
    try:
        from pypdf import PdfReader
    except ImportError:
        import shutil
        import subprocess
        if shutil.which("pdftotext"):
            return subprocess.run(["pdftotext", "-layout", str(path), "-"], capture_output=True, text=True, check=True).stdout
        raise RuntimeError("Reading a PDF needs pypdf (pip install pypdf) or pdftotext.")
    return "\n".join(page.extract_text() or "" for page in PdfReader(str(path)).pages)
