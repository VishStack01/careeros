"""The public job board build and the tags it shows."""

import gzip
import json
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone

from careeros import site, tags
from careeros.cli import main


def rec(i, title, company, posted_days=1, loc="remote-worldwide", text="We use Python and React. 0-1 years.", closed=""):
    posted = (datetime.now(timezone.utc) - timedelta(days=posted_days)).strftime("%Y-%m-%dT%H:%M:%SZ")
    facts = {"expMin": 0.0, "fresherOk": True, "loc": loc, "locQuote": "Remote", "salaryLow": 10.0, "salaryHigh": 14.0,
             "salaryQuote": "₹10-14 LPA", "closedQuote": closed}
    return {"id": f"job-{i}", "company": company, "title": title, "url": f"https://jobs.example.com/{i}", "source": "Greenhouse",
            "location": "Remote", "workMode": "remote", "postedAt": posted, "salary": "", "summary": text[:100], "via": "careers",
            "facts": facts, "tags": tags.tag(title, text, facts)}, {"id": f"job-{i}", "text": text}


def write_feed(d, n=250):
    d.mkdir(parents=True, exist_ok=True)
    rows = [rec(i, f"AI Engineer {i}", f"Co {i % 30}") for i in range(n)]
    rows.append(rec(n, "Old Role", "Co Old", posted_days=90))
    rows.append(rec(n + 1, "Closed Role", "Co Closed", closed="This position has been filled."))
    with gzip.open(d / "india.jsonl.gz", "wt") as f, gzip.open(d / "full.jsonl.gz", "wt") as g:
        for r, t in rows:
            f.write(json.dumps(r) + "\n")
            g.write(json.dumps(t) + "\n")
    (d / "summary.json").write_text(json.dumps({"generatedAt": "2026-10-12T10:00:00Z", "boards": 306, "companies": 1396, "remoteBoards": {"a": 1}}))


def test_site_build(tmp_path):
    write_feed(tmp_path / "feed")
    demo = tmp_path / "demo.html"
    demo.write_text("<html>demo</html>")
    meta = site.build(tmp_path / "feed", tmp_path / "site", demo=demo, base_url="https://example.github.io/careeros/", log=lambda *_: None)
    out = tmp_path / "site"
    assert meta["jobs"] == 250  # the 90-day-old and the closed listing are left out
    data = json.loads((out / "data" / "jobs.json").read_text())
    j = data["jobs"][0]
    assert {"id", "t", "c", "w", "lv", "sk", "u"} <= j.keys() and j["w"] == "ww" and j["lv"] == "Fresher" and "Python" in j["sk"]
    one = json.loads((out / "data" / "jobs" / f"{j['id']}.json").read_text())
    assert one["text"].startswith("We use Python") and one["facts"][0]["k"] == "Experience"
    p1 = json.loads((out / "api" / "jobs.json").read_text())
    assert p1["meta"]["total"] == 250 and p1["meta"]["last_page"] == 3 and len(p1["data"]) == 100
    assert p1["links"]["next"] == "https://example.github.io/careeros/api/jobs/page-2.json" and p1["links"]["prev"] is None
    assert p1["data"][0]["description"] and p1["data"][0]["url"].startswith("https://")
    assert len(json.loads((out / "api" / "jobs" / "page-3.json").read_text())["data"]) == 50
    rss = ET.fromstring((out / "feed.xml").read_text())
    assert len(rss.findall("./channel/item")) == 100
    assert (out / "index.html").read_text().startswith("<!doctype html>")
    assert (out / "demo" / "index.html").exists() and (out / ".nojekyll").exists()
    companies = json.loads((out / "data" / "companies.json").read_text())
    assert sum(c["jobs"] for c in companies) == 250


def test_site_cli(tmp_path):
    write_feed(tmp_path / "feed", n=3)
    main(["site", "--feed", str(tmp_path / "feed"), "--out", str(tmp_path / "s"), "--demo", str(tmp_path / "missing.html")])
    assert json.loads((tmp_path / "s" / "data" / "jobs.json").read_text())["meta"]["jobs"] == 3


def test_tags():
    t = tags.tag("Junior AI Engineer", "Python, FastAPI and LLMs with RAG. Visa sponsorship is available.", {"expMin": 0})
    assert t["level"] == "Fresher" and t["categories"] == ["AI & ML"] and t["skills"][:2] == ["Python", "FastAPI"]
    assert t["perks"] == ["Visa sponsorship"]
    assert tags.tag("Backend Engineer", "We do not offer visa sponsorship.", {"expMin": 3})["perks"] == []
    assert tags.tag("Software Engineer Intern", "", {})["level"] == "Internship"
    assert tags.tag("Staff Engineer", "", {"senior": True, "expMin": 8})["level"] == "Senior"
    assert tags.tag("Data Analyst", "Contract role. Employment type: Contract", {"expMin": 2})["type"] == "Contract"
