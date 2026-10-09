"""The India feed: more hiring systems, board discovery, the scan and personal filtering."""

import csv
import gzip
import json
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path

import pytest

from careeros import discover, feed, scan
from careeros.cli import main
from careeros.gates import apply_decision
from careeros.settings import Settings
from careeros.sources import aggregators, breezy, greenhouse, http, lever, personio, recruitee, smartrecruiters, workable

FIX = Path(__file__).parent / "fixtures"
NOW = datetime(2026, 10, 9, 6, 0, tzinfo=timezone.utc)
BROAD = Settings(role_keywords=Settings().role_keywords + ["backend", "data engineer", "software engineer"])


def load(name):
    return json.loads((FIX / name).read_text())


# ------------------------------------------------------------------ scouts

def test_workable_normalize():
    jobs = [workable.normalize(j, "Acme Robotics") for j in load("workable.json")["jobs"]]
    junior, staff = jobs
    assert junior.location == "Chennai, Tamil Nadu, India"
    assert junior.posted_at == "2026-10-05"
    assert "0-1 years" in junior.description and "<li>" not in junior.description
    assert staff.work_mode == "remote"
    assert not apply_decision(junior, Settings(), NOW).kept  # default roles are AI-focused
    d = apply_decision(junior, BROAD, NOW)
    assert d.kept and d.region == "south-india"


def test_smartrecruiters_list_then_detail(monkeypatch):
    data = load("smartrecruiters_list.json")
    monkeypatch.setattr(smartrecruiters, "get_json",
                        lambda url, **kw: load("smartrecruiters_detail.json") if "/postings/744" in url else data)
    jobs = smartrecruiters.fetch("AcmeTech")
    assert [j.title for j in jobs] == ["Associate Data Scientist", "Sales Manager"]
    ds = jobs[0]
    assert ds.url == "https://jobs.smartrecruiters.com/AcmeTech/744000011111"
    assert ds.work_mode == "hybrid" and ds.raw["needs_detail"]
    smartrecruiters.describe(ds)
    assert "0-2 years" in ds.description and not ds.raw["needs_detail"]


def test_smartrecruiters_pages_until_total(monkeypatch):
    calls = []

    def fake(url, **kw):
        calls.append(url)
        off = int(url.rsplit("offset=", 1)[1])
        items = [{"id": str(off + i), "name": f"Engineer {off + i}", "location": {"city": "Pune", "country": "in"}} for i in range(100 if off < 200 else 30)]
        return {"totalFound": 230, "content": items}

    monkeypatch.setattr(smartrecruiters, "get_json", fake)
    assert len(smartrecruiters.fetch("Big")) == 230 and len(calls) == 3


def test_recruitee_normalize_dates_salary_and_drafts(monkeypatch):
    monkeypatch.setattr(recruitee, "get_json", lambda url, **kw: load("recruitee.json"))
    jobs = recruitee.fetch("acme", "Acme")
    assert len(jobs) == 1  # the draft is dropped
    j = jobs[0]
    assert j.posted_at == "2026-10-04T10:00:00+00:00"
    assert j.work_mode == "remote" and j.salary_text.startswith("₹1200000")
    d = apply_decision(j, Settings(salary_floor_lpa=7), NOW)
    assert d.kept and d.region == "remote-india"


def test_breezy_normalize():
    jobs = [breezy.normalize(j, "Acme") for j in load("breezy.json")]
    assert jobs[0].location == "Bengaluru, IN" and jobs[0].work_mode != "remote"
    assert jobs[1].work_mode == "remote"


def test_personio_normalize():
    root = ET.fromstring((FIX / "personio.xml").read_text())
    j = personio.normalize(root.find("position"), "Acme", "acme")
    assert j.title == "Junior Data Engineer" and j.url == "https://acme.jobs.personio.de/job/1234567"
    assert j.raw["experience_header"] == "0-1 years"
    assert "Fresh graduates" in j.description
    assert apply_decision(j, BROAD, NOW).kept


def test_http_fails_fast_on_missing_board(monkeypatch):
    import urllib.error
    calls = []

    def boom(req, timeout=0, context=None):
        calls.append(req.full_url)
        raise urllib.error.HTTPError(req.full_url, 404, "Not Found", {}, None)

    monkeypatch.setattr(http.urllib.request, "urlopen", boom)
    with pytest.raises(http.FetchError) as e:
        http.get_json("https://example.invalid/missing", retries=3, min_interval=0)
    assert e.value.status == 404 and len(calls) == 1


# ------------------------------------------------------------------ remote job boards

AGG = json.loads((FIX / "aggregators.json").read_text())


def fake_agg_json(url, **kw):
    if "remoteok" in url:
        return AGG["remoteok"]
    if "remotive" in url:
        return AGG["remotive"]
    if "himalayas" in url:
        return AGG["himalayas"]
    if "jobicy" in url:
        return AGG["jobicy"]
    if "search_by_date" in url:
        return AGG["hn_thread"]
    if "algolia.com/api/v1/items" in url:
        return AGG["hn_items"]
    raise http.FetchError("unexpected " + url)


@pytest.fixture
def agg(monkeypatch):
    monkeypatch.setattr(aggregators, "get_json", fake_agg_json)
    monkeypatch.setattr(aggregators, "get_text", lambda url, **kw: (FIX / "wwr.rss").read_text())


def test_remote_boards_normalize(agg):
    ok = aggregators.remoteok()
    assert [j.title for j in ok] == ["Junior Python Developer", "Account Executive"]  # terms notice skipped
    assert ok[0].location == "Remote - Worldwide" and ok[0].work_mode == "remote" and ok[0].salary_text.startswith("$30,000")
    rv = aggregators.remotive()
    assert rv[0].location == "Remote - USA Only" and rv[1].posted_at == "2026-10-07T08:00:00Z"
    assert aggregators.himalayas()[0].location == "Remote - Worldwide"
    assert aggregators.jobicy()[0].posted_at == "2026-10-06T12:31:20Z"
    wwr = aggregators.weworkremotely()
    assert (wwr[0].company, wwr[0].title, wwr[0].location) == ("Pixelworks", "Frontend Developer", "Remote - Anywhere in the World")


def test_remote_boards_pass_the_location_gate(agg):
    s = Settings(role_keywords=Settings().role_keywords + ["developer", "analyst"])
    by_title = {j.title: j for j in aggregators.remotive() + aggregators.remoteok() + aggregators.jobicy() + aggregators.weworkremotely()}
    assert apply_decision(by_title["AI Engineer (Entry Level)"], s, NOW).region == "remote-india"
    assert apply_decision(by_title["Junior Python Developer"], s, NOW).region == "remote-global"
    assert apply_decision(by_title["Data Analyst"], s, NOW).region == "remote-global"  # APAC includes India
    d = apply_decision(by_title["Machine Learning Engineer"], s, NOW)
    loc = next(c for c in d.checks if c.gate == "Location")
    assert not loc.passed and "US" in loc.value


def test_hn_who_is_hiring(agg):
    jobs = aggregators.hn_who_is_hiring()
    assert len(jobs) == 2  # the unstructured comment is ignored
    quill = jobs[0]
    assert quill.company == "Quill" and quill.title == "Founding AI Engineer"
    assert "REMOTE" in quill.location and quill.work_mode == "remote"
    assert quill.url == "https://news.ycombinator.com/item?id=4101"


def test_scan_reuses_board_cache_until_due(tmp_path, monkeypatch):
    calls = []

    def board():
        calls.append(1)
        return [aggregators._remote_job("Kite", "AI Engineer", "https://x.example/1", "Remotive", "Worldwide", "", "2026-10-07T00:00:00Z")]

    monkeypatch.setitem(aggregators.AGGREGATORS, "remotive", board)
    now = datetime.now(timezone.utc)
    recs, err, fresh = scan.scan_aggregator("remotive", tmp_path, now)
    assert fresh and err is None and recs[0]["via"] == "board"
    recs2, _, fresh2 = scan.scan_aggregator("remotive", tmp_path, now)
    assert not fresh2 and recs2 == recs and len(calls) == 1


# ------------------------------------------------------------------ discovery

def test_names_match():
    assert discover.names_match("Sarvam AI", "Sarvam")
    assert discover.names_match("Razorpay", "Razorpay Software Pvt Ltd")
    assert not discover.names_match("Zeta", "Zetwerk")


def test_accept_rules():
    india = {"name": "Acme", "category": "saas"}
    assert discover.accept(india, {"board_name": "Other Co", "locations": ["Bengaluru"]}) == (False, "name-mismatch")
    assert discover.accept(india, {"board_name": "", "locations": ["New York, NY", "London"]}) == (False, "no-india-roles")
    assert discover.accept(india, {"board_name": "", "locations": ["Remote", "London"]})[0]
    assert discover.accept(india, {"board_name": "Acme", "locations": ["Austin, TX"]}) == (True, "name")
    glob = {"name": "Acme", "category": "remote-first-global"}
    assert discover.accept(glob, {"board_name": "", "locations": ["Berlin"]})[0]
    # Some systems answer for any name with an empty board: never proof.
    assert discover.accept(india, {"board_name": "Acme", "locations": []}) == (False, "empty")
    assert discover.accept(glob, {"board_name": "", "locations": []}) == (False, "empty")


def test_empty_board_is_retried_sooner_and_old_empty_mappings_rechecked(tmp_path, monkeypatch):
    monkeypatch.setattr(discover, "probe", lambda ats, slug: {"board_name": slug, "locations": []} if ats == "workable" else None)
    res = discover.discover_one({"name": "Gupshup", "slugs": ["gupshup"]})
    assert res["status"] == "unmapped" and res["retryDays"] == 3
    companies = tmp_path / "c.csv"
    companies.write_text("name,category,city,website,slugs,ats,token,source\nGupshup,ai-native,Bengaluru,,gupshup,,,curated\n")
    cache = tmp_path / "boards.json"
    cache.write_text(json.dumps({"companies": {"Gupshup": {"status": "mapped", "ats": "workable", "token": "gupshup", "confidence": "name-empty", "checkedAt": "2026-10-09T10:00:00Z"}}}))
    out = discover.run(companies, cache, workers=1, log=lambda *_: None)
    assert out["companies"]["Gupshup"]["status"] == "unmapped"


def test_http_backs_off_on_429(monkeypatch):
    import urllib.error
    calls, sleeps = [], []

    def flaky(req, timeout=0, context=None):
        calls.append(1)
        if len(calls) == 1:
            raise urllib.error.HTTPError(req.full_url, 429, "Too Many Requests", {"Retry-After": "1"}, None)

        class R:
            def __enter__(self): return self
            def __exit__(self, *a): return False
            def read(self): return b'{"ok": true}'
        return R()

    monkeypatch.setattr(http.urllib.request, "urlopen", flaky)
    monkeypatch.setattr(http.time, "sleep", lambda s: sleeps.append(s))
    assert http.get_json("https://slow.example/x", min_interval=0) == {"ok": True}
    assert len(calls) == 2 and 1.0 in sleeps


def test_discover_one_tries_known_token_then_slugs(monkeypatch):
    seen = []

    def probe(ats, slug):
        seen.append((ats, slug))
        if (ats, slug) == ("lever", "acme-labs"):
            return {"board_name": "", "locations": ["Hyderabad, India"]}
        return None

    monkeypatch.setattr(discover, "probe", probe)
    res = discover.discover_one({"name": "Acme Labs", "category": "saas", "ats": "ashby", "token": "acmeoldtoken", "slugs": ["acmelabs", "acme-labs"]})
    assert seen[0] == ("ashby", "acmeoldtoken")
    assert res["status"] == "mapped" and res["ats"] == "lever" and res["token"] == "acme-labs" and res["confidence"] == "slug+india"
    assert discover.discover_one({"name": "Nope", "slugs": ["nope"]})["status"] == "unmapped"


def test_discover_run_caches_and_skips_mapped(tmp_path, monkeypatch):
    companies = tmp_path / "companies.csv"
    with companies.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["name", "category", "city", "website", "slugs", "ats", "token", "source"])
        w.writerow(["Acme", "saas", "Bengaluru", "acme.example", "acme", "", "", "curated"])
        w.writerow(["Hidden", "fintech", "Chennai", "hidden.example", "hidden", "", "", "curated"])
    calls = []

    def probe(ats, slug):
        calls.append(slug)
        return {"board_name": "Acme", "locations": ["Bengaluru"]} if slug == "acme" else None

    monkeypatch.setattr(discover, "probe", probe)
    cache = tmp_path / "boards.json"
    out = discover.run(companies, cache, workers=2, log=lambda *_: None)
    assert out["companies"]["Acme"]["status"] == "mapped" and out["companies"]["Hidden"]["status"] == "unmapped"
    assert out["stats"]["mapped"] == 1
    calls.clear()
    discover.run(companies, cache, workers=2, log=lambda *_: None)
    assert calls == []  # nothing due: one mapped, one checked moments ago


# ------------------------------------------------------------------ scan + filter

@pytest.fixture
def boards(tmp_path, monkeypatch):
    monkeypatch.setitem(scan.SCOUTS, "greenhouse", lambda token, company=None: [greenhouse.normalize(j, company or token) for j in load("greenhouse.json")["jobs"]])
    monkeypatch.setitem(scan.SCOUTS, "lever", lambda token, company=None: [lever.normalize(j, company or token) for j in load("lever.json")])
    monkeypatch.setitem(scan.SCOUTS, "workable", lambda token, company=None: [workable.normalize(j, company or token) for j in load("workable.json")["jobs"]])

    def broken(token, company=None):
        raise http.FetchError("HTTP 404", 404)

    monkeypatch.setitem(scan.SCOUTS, "ashby", broken)
    monkeypatch.setattr(scan, "AGGREGATORS", {
        "remotive": lambda: [aggregators._remote_job("Kite Labs", "AI Engineer (Entry Level)", "https://remotive.com/x/2", "Remotive", "India",
                                                     "Freshers welcome.", "2026-10-07T08:00:00Z"),
                             # The same role as Example Labs' own posting: the company page wins.
                             aggregators._remote_job("Example Labs", "AI Engineer, Agents", "https://remotive.com/x/3", "Remotive", "Worldwide",
                                                     "", "2026-10-08T08:00:00Z")],
    })
    path = tmp_path / "boards.json"
    path.write_text(json.dumps({"companies": {
        "Example Labs": {"status": "mapped", "ats": "greenhouse", "token": "examplelabs", "category": "ai-native", "city": "Bengaluru"},
        "Sample Corp": {"status": "mapped", "ats": "lever", "token": "samplecorp", "category": "saas", "city": "Pune"},
        "Acme Robotics": {"status": "mapped", "ats": "workable", "token": "acme", "category": "mobility-industrial-climate-space", "city": "Chennai"},
        "Gone Co": {"status": "mapped", "ats": "ashby", "token": "gone", "category": "saas"},
        "Custom Site Co": {"status": "unmapped", "category": "fintech", "city": "Hyderabad", "website": "custom.example"},
    }}))
    return path


def read_feed(path):
    with gzip.open(path, "rt", encoding="utf-8") as f:
        return [json.loads(line) for line in f]


def test_scan_writes_feed(boards, tmp_path):
    out = tmp_path / "feed"
    summary = scan.run(boards, out, workers=4, log=lambda *_: None)
    recs = {r["title"]: r for r in read_feed(out / "india.jsonl.gz")}
    # Tech roles in India or remote only: no "Account Executive", no US-only onsite roles.
    assert "Account Executive" not in recs
    assert {"AI Engineer, Agents", "Junior AI Automation Engineer", "Junior Backend Engineer"} <= set(recs)
    ai = recs["AI Engineer, Agents"]
    assert ai["company"] == "Example Labs" and ai["category"] == "ai-native" and ai["geo"] == "south"
    assert "expMin" in ai["facts"] and len(ai["summary"]) <= 1500
    assert summary["errors"] == 1 and json.loads(boards.read_text())["companies"]["Gone Co"]["stale"]
    assert recs["AI Engineer (Entry Level)"]["via"] == "board" and recs["AI Engineer, Agents"]["via"] == "careers"
    assert summary["remoteBoards"] == {"remotive": 2}
    rows = list(csv.reader((out / "unmapped.csv").open()))
    assert rows[1][0] == "Custom Site Co"


def test_filter_feed_keeps_skips_and_dedupes(boards, tmp_path):
    scan.run(boards, tmp_path / "feed", workers=4, log=lambda *_: None)
    known = tmp_path / "known"
    known.mkdir()
    (known / "x.json").write_text(json.dumps([{"id": "old", "data": {"company": "Sample Corp", "title": "Junior AI Automation Engineer", "url": "https://elsewhere.example/1"}}]))
    s = feed.settings_from_dashboard({
        "maxRequiredYears": 1, "maxPostingAgeDays": 25, "salaryFloorLpa": 7, "targetRoles": ["Backend", "Software Engineer"],
        "locations": ["South India (any work mode)", "Rest of India (remote only)", "Remote worldwide (first priority)"],
    })
    assert (s.location.south_india, s.location.rest_of_india, s.location.abroad) == ("any", "remote", "remote")
    idx = feed.run(str(tmp_path / "feed" / "india.jsonl.gz"), s, str(known), tmp_path / "new", now=NOW)
    assert idx["alreadyKnown"] == 1  # matched by company + title even with a different URL
    kept = {json.loads(p.read_text())["title"]: json.loads(p.read_text()) for p in (tmp_path / "new" / "kept").glob("*.json")}
    assert "AI Engineer, Agents" in kept and "Junior Backend Engineer" in kept
    assert kept["AI Engineer, Agents"]["foundVia"] == "careers-feed"
    assert kept["AI Engineer (Entry Level)"]["foundVia"] == "remote-board" and kept["AI Engineer (Entry Level)"]["source"] == "Remotive"
    doc = kept["Junior Backend Engineer"]
    assert doc["stage"] == "found" and doc["region"] == "south-india" and doc["foundVia"] == "careers-feed"
    assert doc["brief"]["sources"][0]["url"].startswith("https://apply.workable.com/")
    assert all(c["passed"] for c in doc["checks"])
    skipped = [json.loads(p.read_text()) for p in (tmp_path / "new" / "skipped").glob("*.json")]
    for d in skipped:  # near-misses only: one failed gate, with what would change it
        assert d["stage"] == "skipped" and d["skip"]["wouldChange"]
    assert set(idx["kept"]) == {p.stem for p in (tmp_path / "new" / "kept").glob("*.json")}


def test_filter_feed_finds_closed_and_expired_roles(boards, tmp_path):
    scan.run(boards, tmp_path / "feed", workers=4, log=lambda *_: None)
    known = tmp_path / "known"
    known.mkdir()
    docs = {
        # Was on Example Labs' board, which was read fine this scan, and is gone now: closed.
        "closed-one": {"company": "Example Labs", "title": "Old Role", "url": "https://boards.greenhouse.io/examplelabs/jobs/999", "stage": "found", "foundVia": "careers-feed", "postedAt": "2026-10-01T00:00:00Z"},
        # Gone Co's board errored this scan, so its roles can't be judged.
        "board-down": {"company": "Gone Co", "title": "ML Engineer", "url": "https://jobs.ashbyhq.com/gone/1", "stage": "found", "foundVia": "careers-feed", "postedAt": "2026-10-05T00:00:00Z"},
        # Posted before the 25-day window.
        "too-old": {"company": "Somewhere", "title": "AI Engineer", "url": "https://x.example/2", "stage": "found", "foundVia": "agent", "postedAt": "2026-09-01T00:00:00Z"},
        # Applied roles are never touched.
        "applied": {"company": "Example Labs", "title": "Gone But Applied", "url": "https://boards.greenhouse.io/examplelabs/jobs/998", "stage": "applied", "foundVia": "careers-feed", "postedAt": "2026-10-01T00:00:00Z"},
        # Found by the agent on another site: the feed can't say it closed.
        "agent-found": {"company": "Elsewhere", "title": "AI Engineer", "url": "https://y.example/3", "stage": "found", "foundVia": "agent", "postedAt": "2026-10-06T00:00:00Z"},
    }
    for k, v in docs.items():
        (known / f"{k}.json").write_text(json.dumps({"id": k, "data": v}))
    idx = feed.run(str(tmp_path / "feed" / "india.jsonl.gz"), Settings(), str(known), tmp_path / "new", now=NOW)
    assert idx["gone"] == ["closed-one"] and idx["expired"] == ["too-old"]
    assert idx["feed"]["boards"] == 4


def test_filter_feed_collapses_same_role_in_many_cities(tmp_path):
    base = {"company": "Tether", "title": "AI Technical Product Manager (100% remote)", "source": "Ashby", "location": "Remote", "workMode": "remote",
            "postedAt": "2026-10-08T00:00:00Z", "salary": "", "experienceHeader": "", "summary": "Work from anywhere.", "via": "careers",
            "facts": {"expMin": None, "fresherOk": None, "scope": "worldwide", "scopeEligible": True, "scopeQuote": "anywhere"}}
    path = tmp_path / "f.jsonl"
    path.write_text("\n".join(json.dumps(base | {"id": f"t-{i}", "url": f"https://jobs.ashbyhq.com/tether/{i}"}) for i in range(5)))
    s = Settings(role_keywords=Settings().role_keywords + ["product manager"])
    idx = feed.run(str(path), s, None, tmp_path / "new", now=NOW, summary={})
    assert len(idx["kept"]) == 1 and idx["duplicates"] == 4


def test_filter_feed_cli(boards, tmp_path, capsys):
    scan.run(boards, tmp_path / "feed", workers=4, log=lambda *_: None)
    sj = tmp_path / "settings.json"
    sj.write_text(json.dumps({"id": "profile", "data": {"maxRequiredYears": 1, "maxPostingAgeDays": 25, "locations": ["South India (any work mode)"]}}))
    main(["filter-feed", "--feed", str(tmp_path / "feed" / "india.jsonl.gz"), "--settings-json", str(sj), "--out", str(tmp_path / "new")])
    out = json.loads(capsys.readouterr().out)
    assert out["feedRecords"] >= 3 and "kept" in out


# ------------------------------------------------------------------ platform registry

def test_platform_registry_is_valid_and_rotates():
    from careeros import platforms
    ps = platforms.load()
    assert len(ps) >= 80 and len({p["name"] for p in ps}) == len(ps)
    for p in ps:
        assert p["access"] in {"feed", "fetch", "login", "alerts", "planned"} and p["competition"] in {"low", "medium", "high"}
    runs = [platforms.for_run(ps, i) for i in range(platforms.ROTATIONS)]
    every = {p["name"] for p in ps if p.get("every_run") and p["access"] in ("fetch", "login")}
    assert all(every <= {p["name"] for p in r} for r in runs)
    covered = set().union(*({p["name"] for p in r} for r in runs))
    agent = {p["name"] for p in ps if p["access"] in ("fetch", "login") and p["kind"] != "company-list"}
    assert covered == agent  # every agent platform is visited at least once per rotation
    assert not any(p["access"] == "alerts" for r in runs for p in r)  # never automate the big boards


def test_platforms_cli_json(capsys):
    main(["platforms", "--run", "1", "--json"])
    out = json.loads(capsys.readouterr().out)
    assert out["summary"]["total"] >= 80 and out["thisRun"]


def test_dashboard_title_exclusions():
    s = feed.settings_from_dashboard({"targetRoles": ["Engineer"], "titleExclude": ["Sales", "Mechanical"]})
    from careeros.gates import gate_role
    from careeros.models import Job
    assert gate_role(Job(company="X", title="Backend Engineer", url="", source="t"), s).passed
    assert not gate_role(Job(company="X", title="Sales Engineer", url="", source="t"), s).passed
