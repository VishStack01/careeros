"""Posting signals: work authorization, agency postings, legitimacy, re-listing, archetypes, liveness."""

from datetime import datetime, timedelta, timezone

import pytest

from careeros import gates, liveness, signals
from careeros.models import Job, iso
from careeros.settings import Settings
from careeros.sources.http import FetchError


@pytest.mark.parametrize("text,kind,country", [
    ("Applicants must be authorized to work in the United States without sponsorship.", "local", "US"),
    ("You must have the right to work in the UK.", "local", "UK"),
    ("US citizens only. Remote.", "citizenship", "US"),
    ("Must hold an active TS/SCI clearance.", "clearance", "US"),
    ("Candidates must be eligible to work in India.", "local", "India"),
    ("We are unable to sponsor visas at this time.", "no-sponsorship", ""),
])
def test_work_authorization(text, kind, country):
    wa = signals.work_authorization(text)
    assert wa["kind"] == kind and wa["country"] == country and wa["quote"]


def test_no_work_authorization_signal():
    for text in ("Visa sponsorship is available.", "Work authorization in the US is not required.", "We hire anywhere."):
        assert signals.work_authorization(text) == {}


def test_work_auth_blocks_only_what_rules_india_out():
    us = signals.work_authorization("US citizens only.")
    no_visa = signals.work_authorization("We do not offer visa sponsorship.")
    india = signals.work_authorization("Must be authorized to work in India.")
    assert signals.work_auth_blocks(us, "remote-worldwide") and signals.work_auth_blocks(us, "abroad")
    assert not signals.work_auth_blocks(us, "india")  # an India-located role
    assert not signals.work_auth_blocks(no_visa, "remote-open")  # remote from India needs no visa
    assert signals.work_auth_blocks(no_visa, "abroad")
    assert not signals.work_auth_blocks(india, "remote-open")


def test_work_auth_gate():
    now = datetime.now(timezone.utc)
    job = Job(company="Acme", title="AI Engineer", url="https://x.example/1", source="Greenhouse", location="Remote - Anywhere",
              work_mode="remote", description="Build agents in Python. 0-1 years. Remote anywhere in the world. US citizens only.",
              posted_at=iso(now - timedelta(days=1)))
    d = gates.evaluate(job, Settings(), now)
    wa = next(c for c in d.checks if c.gate == "Work authorization")
    assert not d.kept and not wa.passed and "US citizenship" in wa.value and "citizens only" in wa.quote
    job.description = job.description.replace("US citizens only.", "We don't sponsor visas.")
    d = gates.evaluate(job, Settings(), now)
    assert d.kept and "doesn't need" in next(c for c in d.checks if c.gate == "Work authorization").value


def test_agency_and_archetype():
    assert "our client" in signals.agency("We are hiring on behalf of our client, a fintech.")
    assert signals.agency("Our clients love the product.") == ""
    assert signals.archetype("Forward Deployed Engineer") == "Forward deployed"
    assert signals.archetype("AI Agent Developer") == "Agentic & automation"
    assert signals.archetype("ML Platform Engineer, Inference") == "AI platform & LLMOps"
    assert signals.archetype("Product Designer, AI") == "AI product"
    assert signals.archetype("Accountant") == ""


def test_legitimacy_tiers():
    now = datetime.now(timezone.utc)
    good = signals.legitimacy("AI Engineer", "Python, FastAPI, PostgreSQL and LLMs. " * 20,
                              {"expMin": 0, "salaryHigh": 12, "salaryQuote": "₹10-12 LPA"}, iso(now - timedelta(days=3)), now=now)
    assert good["tier"] == "high" and good["label"] == "Looks real"
    shady = signals.legitimacy("Junior Developer", "Great team.", {"expMin": 5, "expQuote": "5+ years"},
                               iso(now - timedelta(days=90)), {"count": 2, "since": "2026-07-01"}, now=now)
    assert shady["tier"] == "suspicious"
    notes = {s["signal"]: s for s in shady["signals"]}
    assert notes["Re-listed"]["status"] == "concern" and notes["Consistent"]["status"] == "concern" and notes["Age"]["status"] == "concern"
    agency = signals.legitimacy("AI Engineer", "On behalf of our client we need Python and AWS and Docker skills.", {"expMin": 1},
                                iso(now - timedelta(days=40)), now=now)
    assert agency["tier"] == "caution" and any(s["signal"] == "Employer named" for s in agency["signals"])


def test_repost_history(tmp_path):
    day = lambda n: datetime(2026, 9, 1, tzinfo=timezone.utc) + timedelta(days=n)
    h = signals.RepostHistory(tmp_path / "h.json.gz")
    a = {"id": "a", "url": "https://x/1", "company": "Acme Pvt Ltd", "title": "AI Engineer (Remote)"}
    b = {"id": "b", "url": "https://x/2", "company": "Acme", "title": "Engineer, AI"}  # same words, new listing
    sibling = {"id": "c", "url": "https://x/3", "company": "Acme", "title": "AI Engineer"}
    h.observe([a], day(0))
    h.observe([a], day(5))
    h.observe([b], day(9))  # a disappeared after day 5, b appears on day 9: a re-listing
    assert h.reposts("Acme", "Engineer, AI", "https://x/2")["count"] == 1
    h2 = signals.RepostHistory(tmp_path / "h2.json.gz")
    h2.observe([a], day(0))
    h2.observe([a, sibling], day(3))  # a still open when c appears: parallel openings, not a repost
    assert h2.reposts("Acme", "AI Engineer", "https://x/3")["count"] == 0
    other = {"id": "d", "url": "https://x/4", "company": "Acme", "title": "Senior AI Engineer"}
    h.observe([other], day(12))
    assert h.reposts("Acme", "Senior AI Engineer", "https://x/4")["count"] == 0  # a level word makes it another role
    h.save()
    again = signals.RepostHistory(tmp_path / "h.json.gz")
    assert again.reposts("Acme", "Engineer, AI", "https://x/2")["count"] == 1
    again.prune(day(400))
    assert again.data == {}


def _fake(json_map=None, text_map=None):
    def fj(url):
        v = (json_map or {}).get(url)
        if isinstance(v, int):
            raise FetchError(url, v)
        if v is None:
            raise FetchError(url, None)
        return v

    def ft(url):
        v = (text_map or {}).get(url)
        if isinstance(v, int):
            raise FetchError(url, v)
        if v is None:
            raise FetchError(url, None)
        return v
    return fj, ft


def test_liveness_api_routes():
    assert liveness.ats_api("https://job-boards.greenhouse.io/tailscale/jobs/4733404005")[1] == "https://boards-api.greenhouse.io/v1/boards/tailscale/jobs/4733404005"
    assert liveness.ats_api("https://jobs.lever.co/fampay/771cb90b")[1] == "https://api.lever.co/v0/postings/fampay/771cb90b"
    assert liveness.ats_api("https://jobs.ashbyhq.com/langchain/fc86")[0] == "ashby"
    assert liveness.ats_api("https://jobs.smartrecruiters.com/servicenow/744000154931529-ai-engineer")[1].endswith("/servicenow/postings/744000154931529")
    assert liveness.ats_api("https://acme.com/careers/123") is None
    gh = "https://job-boards.greenhouse.io/acme/jobs/1"
    api = "https://boards-api.greenhouse.io/v1/boards/acme/jobs/1"
    assert liveness.check(gh, *_fake({api: {"id": 1, "title": "AI Engineer"}})).status == "open"
    assert liveness.check(gh, *_fake({api: 404})).status == "closed"
    ash = "https://jobs.ashbyhq.com/acme/abc"
    board = "https://api.ashbyhq.com/posting-api/job-board/acme"
    assert liveness.check(ash, *_fake({board: {"jobs": [{"id": "abc"}]}})).status == "open"
    assert liveness.check(ash, *_fake({board: {"jobs": [{"id": "zzz"}]}})).status == "closed"


def test_liveness_page_signals():
    u = "https://acme.com/careers/ai-engineer"
    assert liveness.check(u, *_fake(text_map={u: 404})).status == "closed"
    closed = liveness.check(u, *_fake(text_map={u: "<h1>AI Engineer</h1><p>This position has been filled. Thanks!</p>"}))
    assert closed.status == "closed" and "filled" in closed.evidence
    assert liveness.check(u, *_fake(text_map={u: "<p>Once the application form has been filled out we reply.</p><a class='btn'>Apply now</a>"})).status == "open"
    assert liveness.check(u, *_fake(text_map={u: "<p>Closed-loop control systems.</p><button>Apply for this job</button>"})).status == "open"
    assert liveness.check(u, *_fake(text_map={u: "<p>About us</p>"})).status == "uncertain"
    assert liveness.check(u, *_fake()).status == "uncertain"
    lever = "https://jobs.lever.co/acme/x1"  # Lever's API can 404 a live posting: the page decides
    assert liveness.check(lever, *_fake({"https://api.lever.co/v0/postings/acme/x1": 404}, {lever: "<a href='#'>Apply for this job</a>"})).status == "open"
