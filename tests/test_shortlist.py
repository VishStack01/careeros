"""ATS readiness, market demand, offer-based pay bands and years in titles."""

import gzip
import json

from careeros import ats, extract, market, paydata
from careeros.cli import main

RESUME = """Asha Rao
Bengaluru | +91 98765 43210 | asha@example.com | github.com/asha | linkedin.com/in/asha
SUMMARY
AI engineer who ships RAG systems in Python and FastAPI.
EXPERIENCE
AI Engineer | Acme
Jan 2026 – Present
Built a retrieval service in Python serving 1,200 users with 300 ms median latency.
Cut evaluation time by 40% with an LLM-as-judge harness and 85 regression tests.
Automation Engineer | Beta
Nov 2023 – 2025
Wrote n8n workflows that moved leads between the CRM and email tools for the sales team.
EDUCATION
B.Tech CSE, GITAM University, 2026
SKILLS
Python, FastAPI, React, PostgreSQL, Docker, AWS
PROJECTS
CareerOS: scans 3,000 company job boards every hour and keeps roles with quoted checks.
""" + "Detail line with enough words to look like a real resume line for parsing. " * 12


def test_ats_check_finds_real_problems():
    rep = ats.check(RESUME, pages=2, filename="Asha Rao - Resume.pdf", profile={"fullName": "Asha Rao", "experienceYears": 0.5},
                    terms=["Python", "Kubernetes", "React", "Java", "AWS"])
    by = {c["id"]: c for c in rep["checks"]}
    assert by["text"]["ok"] and by["contact"]["ok"] and by["links"]["ok"] and by["name"]["ok"] and by["headings"]["ok"]
    assert not by["length"]["ok"]  # two pages under 3 years
    assert not by["dates"]["ok"]  # "Nov 2023 – 2025" has no end month
    assert by["filename"]["ok"]
    assert rep["keywordCoverage"] == 0.6 and "Kubernetes" in by["keywords"]["fix"]
    assert 0 < rep["score"] < 100
    one_page = ats.check(RESUME.replace("Nov 2023 – 2025", "Nov 2023 – Mar 2025"), pages=1, profile={"experienceYears": 0.5})
    assert {c["id"]: c["ok"] for c in one_page["checks"]}["dates"] and one_page["score"] > rep["score"]
    assert not ats.check("", 1)["checks"][0]["ok"]  # an image-only PDF


def _rec(i, title, hi=None, band=None, exp=0, loc="south", company=None, skills=("Python",)):
    f = {"expMin": exp, "loc": loc}
    if hi is not None:
        f["salaryHigh"] = hi
    if band:
        f["payBand"] = band
    return {"id": f"r{i}", "company": company or f"Co{i}", "title": title, "facts": f, "tags": {"skills": list(skills)}}


def test_market_funnel_skills_and_gaps(tmp_path):
    recs = [_rec(1, "Software Engineer", hi=30, skills=("Python", "Kubernetes")),
            _rec(2, "AI Engineer", band={"low": 20, "high": 40}, skills=("Python", "PyTorch")),
            _rec(3, "Backend Developer", hi=8),
            _rec(4, "Backend Developer", exp=5, hi=40),
            _rec(5, "Product Designer", hi=40),
            _rec(6, "SDE", loc="abroad", hi=40),
            _rec(7, "Frontend Engineer")]
    out = market.analyze(recs, {"salaryFloorLpa": 15, "maxRequiredYears": 1, "titleExclude": ["Designer"]}, resume="Python and FastAPI")
    assert out["funnel"] == {"openings": 7, "your roles": 6, "your experience": 5, "open to you": 4, "pay stated": 1,
                             "pay estimated": 1, "pay below": 1, "pay unknown": 1}
    sk = {s["skill"]: s for s in out["skills"]}
    assert sk["Python"]["share"] == 1.0 and sk["Python"]["onResume"] and sk["Kubernetes"]["onResume"] is False
    assert set(out["gaps"]) == {"Kubernetes", "PyTorch"} and out["rolesAtFloor"] == 2
    feed = tmp_path / "f.jsonl.gz"
    with gzip.open(feed, "wt", encoding="utf-8") as f:
        f.write("\n".join(json.dumps(r) for r in recs))
    (tmp_path / "s.json").write_text(json.dumps({"data": {"salaryFloorLpa": 15}}))
    (tmp_path / "r.txt").write_text("Python")
    main(["market", "--feed", str(feed), "--settings", str(tmp_path / "s.json"), "--resume", str(tmp_path / "r.txt"), "--json"])


def test_offer_bands_and_curated_priority(tmp_path, monkeypatch):
    offers = [{"company": "Zeta", "yoe": 0.5, "base": 16, "total": 19, "date": "2025-05-01"},
              {"company": "Zeta", "yoe": "1", "base": 18, "total": 22, "date": "2025-06-01"},
              {"company": "Zeta", "yoe": 4, "base": 40, "total": 50, "date": "2025-06-01"},  # too senior
              {"company": "MNC", "yoe": 0, "base": 30, "total": 30, "date": "2025-06-01"},
              {"company": "MNC", "yoe": 0, "base": 30, "total": 30, "date": "2025-06-01"},  # not a company
              {"company": "Solo", "yoe": 0, "base": 25, "total": 25, "date": "2025-06-01"},  # one offer only
              {"company": "Old", "yoe": 0, "base": 25, "total": 25, "date": "2023-01-01"},
              {"company": "Old", "yoe": 0, "base": 25, "total": 25, "date": "2023-02-01"}]
    rows = paydata.offer_bands(offers)
    assert rows == [{"company": "Zeta", "low_lpa": 17.0, "high_lpa": 20.5, "n": 2}]
    out = tmp_path / "offers.csv"
    paydata.write_offers(rows, out)
    curated = tmp_path / "entry.csv"
    curated.write_text("company,aliases,low_lpa,high_lpa,basis,sources\nZeta,,12,14,campus CTC,250cl\n")
    monkeypatch.setattr(paydata, "OFFERS", out)
    monkeypatch.setattr(paydata, "DEFAULT", curated)
    paydata.load.cache_clear()
    try:
        assert paydata.band("Zeta")["low"] == 12  # the curated row wins
        curated.write_text("company,aliases,low_lpa,high_lpa,basis,sources\n")
        paydata.load.cache_clear()
        b = paydata.band("Zeta Pvt Ltd")
        assert b["low"] == 17.0 and "2 offers" in paydata.describe(b) and "leetcode" in paydata.describe(b).lower()
    finally:
        paydata.load.cache_clear()


def test_years_in_titles_count_as_experience():
    assert extract.title_years("Software Engineer- 2- 4years- AI Native") == 2
    assert extract.title_years("ASIC Engineer - 5 years to 13Years") == 5
    assert extract.title_years("Backend (4-8 Yrs), Bangalore") == 4
    assert extract.title_years("SDE-1") is None and extract.title_years("Engineer, 2026 batch") is None
    assert extract.title_seniority("Software Engineering Technical Leader") == "senior"


def test_temporary_work_from_anywhere_is_not_remote():
    perk = "Hybrid roles have the flexibility to work from anywhere for up to 4 weeks per year."
    assert extract.work_mode(location="San Francisco, CA", text=perk) != "remote"
    assert extract.remote_scope("San Francisco, CA", perk).scope == ""
    assert extract.work_mode(text="You also get 4 weeks of work from anywhere each year.") == ""
    assert extract.work_mode(location="Remote", text="Work from anywhere in the world.") == "remote"
