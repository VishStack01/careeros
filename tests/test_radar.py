"""Hiring radar (JobSpy -> employer boards) and the stated-pay tier."""

import csv
import json
from datetime import datetime, timedelta, timezone

from careeros import discover, feed, site, tags
from careeros.settings import Settings
from careeros.sources import radar


def test_board_from_url():
    cases = {
        "https://boards.greenhouse.io/razorpaysoftwareprivatelimited/jobs/123": ("greenhouse", "razorpaysoftwareprivatelimited"),
        "https://job-boards.greenhouse.io/postman/jobs/9": ("greenhouse", "postman"),
        "https://boards.greenhouse.io/embed/job_app?for=acme&token=1": ("greenhouse", "acme"),
        "https://jobs.lever.co/fampay/771cb90b/apply": ("lever", "fampay"),
        "https://jobs.ashbyhq.com/Sarvam/abc": ("ashby", "Sarvam"),
        "https://jobs.smartrecruiters.com/ServiceNow/744000-ai": ("smartrecruiters", "ServiceNow"),
        "https://apply.workable.com/acme-ai/j/ABC123/": ("workable", "acme-ai"),
        "https://acme.recruitee.com/o/ai-engineer": ("recruitee", "acme"),
        "https://acme.breezy.hr/p/123": ("breezy", "acme"),
        "https://acme.jobs.personio.de/job/1": ("personio", "acme"),
    }
    for url, want in cases.items():
        assert radar.board_from_url(url) == want, url
    for url in ("https://in.indeed.com/viewjob?jk=1", "https://www.naukri.com/job-listings-x", "https://acme.com/careers/1", "", "https://apply.workable.com/j/ABC"):
        assert radar.board_from_url(url) is None, url


def test_slugs_and_harvest():
    assert radar.slugs_for("Zeta Suite Technologies Pvt Ltd") == ["zetasuite", "zeta-suite", "zeta"]
    rows = [
        {"site": "indeed", "company": "Postman", "job_url": "https://in.indeed.com/viewjob?jk=1", "job_url_direct": "https://job-boards.greenhouse.io/postman/jobs/9"},
        {"site": "naukri", "company": "Zeta", "job_url": "https://www.naukri.com/job-listings-1", "job_url_direct": None},
        {"site": "naukri", "company": "Zeta", "job_url": "https://www.naukri.com/job-listings-2", "job_url_direct": float("nan")},
        {"site": "naukri", "company": "ABC Staffing Solutions", "job_url": "https://www.naukri.com/x"},
        {"site": "indeed", "company": "nan", "job_url": "https://in.indeed.com/viewjob?jk=2"},
    ]
    h = radar.harvest(rows)
    assert h["boards"] == {("greenhouse", "postman"): {"company": "Postman", "site": "indeed"}}
    assert h["companies"] == {"Zeta": {"site": "naukri", "count": 2}}


def test_search_plans_and_failures():
    calls = []

    def fake(**kw):
        calls.append(kw)
        if kw["site_name"] == ["naukri"] and kw["location"] == "Chennai":
            raise RuntimeError("blocked")
        return [{"site": kw["site_name"][0], "company": "X", "job_url": "u"}]
    cfg = dict(radar.DEFAULTS, terms=["ai engineer"], locations=["Bengaluru", "Chennai"], sites=["indeed", "naukri"])
    logs = []
    rows = radar.search(cfg, scrape=fake, log=logs.append)
    assert len(calls) == 5  # indeed x2 cities + indeed remote + naukri x2
    assert any(c.get("is_remote") and c["country_indeed"] == "India" for c in calls)
    assert len(rows) == 4 and any("failed" in m for m in logs)


def test_merge_adds_verified_boards_and_queues_names(tmp_path):
    cache = {"companies": {"Acme": {"status": "mapped", "ats": "lever", "token": "acme"}}}
    found = {"boards": {("greenhouse", "postman"): {"company": "Postman", "site": "indeed"},
                        ("lever", "acme"): {"company": "Acme", "site": "indeed"},
                        ("ashby", "ghost"): {"company": "Ghost", "site": "indeed"}},
             "companies": {"Zeta": {"site": "naukri", "count": 2}, "Acme Pvt Ltd": {"site": "naukri", "count": 1}}}
    probe = lambda ats, tok: None if tok == "ghost" else {"board_name": "Postman", "locations": ["Bengaluru, India"]}
    out = tmp_path / "radar.csv"
    res = radar.merge(found, cache, out, probe, discover.accept, now=datetime(2026, 10, 23, tzinfo=timezone.utc))
    assert res == {"boardsAdded": 1, "companiesAdded": 1, "radarCompanies": 1}
    e = cache["companies"]["Postman"]
    assert e["status"] == "mapped" and e["ats"] == "greenhouse" and e["confidence"].startswith("radar:") and e["foundVia"] == "indeed"
    rows = list(csv.DictReader(out.open(encoding="utf-8")))
    assert [r["name"] for r in rows] == ["Zeta"] and rows[0]["slugs"] == "zeta" and rows[0]["category"] == "radar"
    # Running again adds nothing new.
    assert radar.merge(found, cache, out, probe, discover.accept)["companiesAdded"] == 0


def test_discover_reads_extra_lists(tmp_path, monkeypatch):
    main = tmp_path / "companies.csv"
    main.write_text("name,category,city,website,slugs,ats,token,source\nAcme,saas,,,acme,,,curated\n", encoding="utf-8")
    extra = tmp_path / "radar.csv"
    extra.write_text("name,category,city,website,slugs,ats,token,source\nZeta,radar,,,zeta,,,radar:naukri\nAcme,radar,,,acme,,,radar\n", encoding="utf-8")
    seen = []
    monkeypatch.setattr(discover, "discover_one", lambda c: seen.append(c["name"]) or {"status": "unmapped", "checkedAt": "x"})
    discover.run(main, tmp_path / "boards.json", workers=1, log=lambda *_: None, extra=[extra])
    assert sorted(seen) == ["Acme", "Zeta"]
    assert json.loads((tmp_path / "boards.json").read_text())["companies"]["Zeta"]["category"] == "radar"


def test_pay_tier_everywhere():
    assert tags.pay_tier({"salaryHigh": 24}) == "20+" and tags.pay_tier({"salaryHigh": 12}) == "10-20"
    assert tags.pay_tier({"salaryHigh": 6}) == "under-10" and tags.pay_tier({}) == ""
    now = datetime.now(timezone.utc)
    iso = lambda d: d.strftime("%Y-%m-%dT%H:%M:%SZ")

    def rec(i, hi, hours):
        f = {"loc": "remote-worldwide", "expMin": 0, "fresherOk": True}
        if hi is not None:
            f.update(salaryLow=hi - 4, salaryHigh=hi, salaryQuote=f"{hi - 4}-{hi} LPA")
        return {"id": f"r{i}", "company": f"Co{i}", "title": "AI Engineer", "url": f"https://x.example/{i}", "source": "Greenhouse",
                "location": "Remote", "workMode": "remote", "postedAt": iso(now - timedelta(hours=hours)), "summary": "Build agents.",
                "facts": f, "tags": tags.tag("AI Engineer", "Build agents.", f)}
    records = [rec(1, None, 1), rec(2, 30, 20), rec(3, 12, 2)]
    res = feed.match(records, Settings(), [], now=now)
    kept = [d for _, d in res["kept"]]
    assert kept[0]["company"] == "Co2" and kept[0]["payTier"] == "20+"  # stated 20 LPA+ first within its region
    assert "payTier" not in kept[1] or kept[1]["payTier"] != "20+"
    c = site.compact(records[1])
    assert c["pt"] == "20+" and c["ph"] == 30
