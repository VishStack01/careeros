"""Documents: rendering the resume, checking the PDF, keyword coverage, cliché check and the posting archive."""

import json
import shutil
from pathlib import Path

import pytest

from careeros import claims, jd, keywords, render, writing
from careeros.sources.http import FetchError

ROOT = Path(__file__).resolve().parents[1]
BRAIN = json.loads((ROOT / "brain" / "brain.example.json").read_text(encoding="utf-8"))
RESUME = json.loads((ROOT / "examples" / "resume.example.json").read_text(encoding="utf-8"))
JD = (ROOT / "examples" / "jd.example.txt").read_text(encoding="utf-8")
PROFILE = {"fullName": "Asha Example", "email": "asha@example.com", "phone": "+91 98765 43210", "city": "Bengaluru"}


def test_resume_html_groups_bullets_and_adds_no_facts():
    h = render.resume_html(RESUME, BRAIN, PROFILE)
    assert h.index("<h2>Summary</h2>") < h.index("<h2>Skills</h2>") < h.index("<h2>Experience</h2>") < h.index("<h2>Projects</h2>")
    assert "AI Automation Intern, Acme Fintech (example)" in h and "Jun 2025 – Jan 2026" in h
    assert "<table" not in h and "<img" not in h
    assert "asha@example.com" in h and 'href="https://github.com/asha-example"' in h
    evil = dict(RESUME, summary="<script>alert(1)</script>")
    assert "<script>alert" not in render.resume_html(evil, BRAIN)


def test_pdf_check_catches_edits_after_the_claims_check():
    text = "Asha Example\nAI Engineer\n" + "\n".join(b["text"] for b in RESUME["bullets"]) + "\nBengaluru +91 98765 43210"
    assert claims.check_pdf(text, RESUME, BRAIN, PROFILE).ok
    padded = text.replace("1,500 tickets", "15,000 tickets")
    rep = claims.check_pdf(padded, RESUME, BRAIN, PROFILE)
    assert not rep.ok and any("15000" in b for b in rep.blocking)
    missing = "Asha Example\n" + RESUME["bullets"][0]["text"]
    assert any("isn't in the PDF" in b for b in claims.check_pdf(missing, RESUME, BRAIN, PROFILE).blocking)
    assert not claims.check_pdf("", RESUME, BRAIN).ok
    # A bullet wrapped across lines, with a hyphen split at the line end, still counts as present.
    wrapped = text.replace("open-source LLM", "open-\nsource LLM")
    assert claims.check_pdf(wrapped, RESUME, BRAIN, PROFILE).ok


@pytest.mark.skipif(not shutil.which("chromium") and not Path("/opt/pw-browsers").exists(), reason="needs Playwright's Chromium")
def test_render_pdf_roundtrip(tmp_path):
    pytest.importorskip("playwright")
    pytest.importorskip("pypdf")
    out = render.to_pdf(render.resume_html(RESUME, BRAIN, PROFILE), tmp_path / "r.pdf")
    rep = claims.check_pdf(render.pdf_text(out), RESUME, BRAIN, PROFILE)
    assert rep.ok, rep.blocking
    cover = render.to_pdf(render.cover_html("Your team triages tickets by hand.\n\nI built TicketRouter.", BRAIN, PROFILE, "Acme"), tmp_path / "c.pdf")
    assert "TicketRouter" in render.pdf_text(cover)


def test_keyword_coverage():
    terms = keywords.extract(JD)
    assert "Python" in terms[:4] and "FastAPI" in terms and "Kubernetes" in terms and "RAG" in terms
    cov = keywords.coverage(terms, RESUME)
    assert "Python" not in cov["missing"] and "Kubernetes" in cov["missing"]
    assert "FastAPI" in cov["thin"]  # in the skills list, not in any bullet
    assert "ATS" not in cov["summary"] and "of" in cov["summary"]
    assert keywords.coverage(["vector databases"], "We used pgvector for search.")["present"] == ["vector databases"]
    stuffed = {"bullets": [{"text": f"Python thing {i}"} for i in range(5)]}
    assert keywords.repeated(stuffed) == ["Python"]


def test_writing_check():
    note = ("I am writing to express my interest in the role. I am passionate about AI and a results-driven team player. "
            "I leveraged cutting-edge tools. I believe I would be a great fit. Thank you for your consideration!")
    found = {f.phrase.lower() for f in writing.check(note)}
    for p in ("i am writing to express", "passionate about", "results-driven", "team player", "leveraged", "cutting-edge", "i believe i would be a great fit"):
        assert p in found, p
    assert not writing.specific("I am a fast learner.")
    good = "Your support team triages 2,000 tickets a week by hand. I built TicketRouter, which tags them at 94% accuracy. Could we talk this week?"
    assert writing.check(good) == [] and writing.specific(good)
    assert any(f.phrase.lower() == "synergy" for f in writing.check("Great synergy.", banned=["synergy"]))


def _fake(json_map=None, text_map=None):
    def get(m):
        def f(url):
            v = (m or {}).get(url)
            if v is None or isinstance(v, int):
                raise FetchError(url, v)
            return v
        return f
    return get(json_map), get(text_map)


def test_archive_jd_api_then_page(tmp_path):
    body = "<p>" + "Build agents in Python. " * 20 + "</p>"
    gh = "https://job-boards.greenhouse.io/acme/jobs/7"
    got = jd.fetch(gh, *_fake({"https://boards-api.greenhouse.io/v1/boards/acme/jobs/7": {"title": "AI Engineer", "content": body.replace("<", "&lt;").replace(">", "&gt;"), "updated_at": "2026-10-01"}}))
    assert got["via"] == "greenhouse api" and got["text"].startswith("Build agents in Python.") and got["title"] == "AI Engineer"
    lever = "https://jobs.lever.co/acme/abc"
    got = jd.fetch(lever, *_fake({"https://api.lever.co/v0/postings/acme/abc": {"text": "AI Engineer", "descriptionPlain": "About the role. " * 20,
                                                                              "lists": [{"text": "Requirements", "content": "<li>Python</li>"}], "createdAt": 1790000000000}}))
    assert "Requirements" in got["text"] and "Python" in got["text"] and got["postedAt"].startswith("2026")
    page = "https://acme.example/careers/ai"
    html = "<html><head><title>AI Engineer | Acme</title><script>var x=1</script></head><body><nav>Menu</nav><main><h1>AI Engineer</h1><p>Must have Python.</p></main>" \
           '<script type="application/ld+json">{"datePosted": "2026-10-02"}</script></body></html>'
    got = jd.fetch(page, *_fake(text_map={page: html}))
    assert got["via"] == "page" and "Must have Python." in got["text"] and "Menu" not in got["text"] and got["postedAt"] == "2026-10-02"
    p = jd.save(got, tmp_path, "Acme")
    md = p.read_text(encoding="utf-8")
    assert md.startswith("# AI Engineer | Acme at Acme") and "Posted: 2026-10-02" in md and "## Job description (archived verbatim)" in md
    with pytest.raises(FetchError):
        jd.fetch(page, *_fake())
