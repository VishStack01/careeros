"""YC jobs listing reader and YC hiring companies for discovery."""

import html
import json
from datetime import datetime, timezone

from careeros import scan
from careeros.cli import main
from careeros.sources import yc

NOW = datetime(2026, 10, 26, 12, 0, tzinfo=timezone.utc)


def _page(postings, attr=True):
    data = {"component": "WaasJobListingsPage", "props": {"jobPostings": postings, "user": {"title": "not a job"}}}
    blob = html.escape(json.dumps(data), quote=True)
    return f'<html><body><div id="app" data-page="{blob}"></div></body></html>' if attr else \
        f'<script id="__NEXT_DATA__" type="application/json">{json.dumps(data)}</script>'


POSTINGS = [
    {"id": 1, "title": "Software Engineer (AI)", "url": "/companies/acme/jobs/AbC-software-engineer-ai", "companyName": "Acme",
     "location": "Bengaluru, KA, IN", "salaryRange": "₹1.8M - ₹3M INR", "minExperience": "Any (new grads ok)",
     "type": "Full-time", "createdAt": "2026-10-25T10:00:00Z", "companyOneLiner": "Agents for accountants."},
    {"id": 2, "title": "Forward Deployed Engineer - India", "url": "https://www.ycombinator.com/companies/litellm/jobs/x-fde",
     "company": {"name": "LiteLLM"}, "location": "Remote (IN)", "salaryRange": "$50K - $90K", "minExperience": "1+ years",
     "lastActive": "3 days ago"},
    {"id": 3, "title": "Staff Engineer", "url": "/companies/beta-labs/jobs/y-staff", "location": "Remote (US)",
     "salaryRange": "$200K - $250K", "minExperience": "6+ years"},
    {"id": 1, "title": "Software Engineer (AI)", "url": "/companies/acme/jobs/AbC-software-engineer-ai", "companyName": "Acme",
     "location": "Bengaluru, KA, IN", "salaryRange": "₹1.8M - ₹3M INR"},  # listed twice on the page
]


def test_parse_reads_postings_from_page_data():
    jobs = yc.parse(_page(POSTINGS), now=NOW)
    assert [j.company for j in jobs] == ["Acme", "LiteLLM", "Beta Labs"]
    a, l, b = jobs
    assert a.url == "https://www.ycombinator.com/companies/acme/jobs/AbC-software-engineer-ai" and a.source == "YC Work at a Startup"
    assert a.salary_text == "₹1.8M - ₹3M INR" and a.raw["experience_header"] == "Any (new grads ok)"
    assert a.posted_at == "2026-10-25T10:00:00Z" and a.description == "Agents for accountants."
    assert l.work_mode == "remote" and l.posted_at == "2026-10-23T12:00:00Z"
    assert yc.parse(_page(POSTINGS, attr=False), now=NOW)[0].title == "Software Engineer (AI)"
    assert yc.parse("<html>nothing here</html>") == []


def test_yc_roles_get_pay_and_experience_facts():
    jobs = yc.parse(_page(POSTINGS), now=NOW)
    recs = [scan.to_feed(j, {"category": "remote-board"}, via="board") for j in jobs]
    a, l, b = (r["facts"] for r in recs)
    assert a["salaryLow"] == 18 and a["salaryHigh"] == 30 and a.get("fresherOk") is True and a["loc"] in ("south", "india")
    assert l["expMin"] == 1 and l["salaryHigh"] > 15
    assert b["expMin"] == 6


def test_fetch_skips_failed_pages_but_not_all():
    pages = ["u1", "u2"]
    assert len(yc.fetch(pages, get=lambda u: _page(POSTINGS) if u == "u1" else (_ for _ in ()).throw(OSError("x")))) == 3
    try:
        yc.fetch(pages, get=lambda u: (_ for _ in ()).throw(OSError("x")))
        raise AssertionError("expected an error")
    except RuntimeError:
        pass


def test_hiring_companies_for_discovery(tmp_path):
    data = [{"name": "Acme AI", "slug": "acme-ai", "isHiring": True, "regions": ["India", "South Asia"], "batch": "Winter 2025"},
            {"name": "Remote Co", "slug": "remoteco", "isHiring": True, "regions": ["Remote", "United States of America"]},
            {"name": "US Only", "slug": "usonly", "isHiring": True, "regions": ["United States of America"]},
            {"name": "Not Hiring", "slug": "nh", "isHiring": False, "regions": ["India"]}]
    rows = yc.hiring_companies(data)
    assert [(r["name"], r["slugs"]) for r in rows] == [("Acme AI", "acme-ai acmeai"), ("Remote Co", "remoteco")]
    assert all(r["category"] == "deep" for r in rows)
    src = tmp_path / "hiring.json"
    src.write_text(json.dumps(data))
    out = tmp_path / "yc.csv"
    main(["yc-companies", "--source", str(src), "--out", str(out)])
    assert out.read_text().count("yc-hiring:") == 2
