"""Deep sweep of the open ATS inventory, and Greenhouse pay ranges."""

import csv
import gzip
import json

from careeros import deep, discover, scan
from careeros.models import Job
from careeros.sources import greenhouse


# ------------------------------------------------------------------ Greenhouse pay ranges

def test_pay_text_picks_the_range_that_applies():
    inr = {"min_cents": 180000000, "max_cents": 300000000, "currency_type": "INR", "title": "India"}
    usd = {"min_cents": 9000000, "max_cents": 13000000, "currency_type": "USD", "title": "US Salary Range"}
    eur = {"min_cents": 6000000, "max_cents": 8000000, "currency_type": "EUR", "title": "Berlin"}
    assert greenhouse.pay_text([usd, inr], india=True) == "₹1,800,000 - ₹3,000,000 /year"
    assert greenhouse.pay_text([usd, inr], india=False) == "₹1,800,000 - ₹3,000,000 /year"  # rupees win when given
    assert greenhouse.pay_text([usd], india=True) == ""  # a US range says nothing about an India role
    assert greenhouse.pay_text([usd], india=False) == "$90,000 - $130,000 /year"
    assert greenhouse.pay_text([eur], india=False) == ""  # no guessed conversion
    assert greenhouse.pay_text([{"max_cents": 0, "currency_type": "INR"}], india=True) == ""
    assert greenhouse.pay_text([], india=True) == ""


def _gh_job(i, desc="Build agents in Python.", loc="Bengaluru, India"):
    return Job(company="Acme", title="AI Engineer", url=f"https://job-boards.greenhouse.io/acme/jobs/{i}", source="Greenhouse",
               location=loc, description=desc, posted_at="2026-10-20T00:00:00Z", raw={"id": i})


def test_greenhouse_pay_looks_up_once_within_budget(monkeypatch):
    calls = []
    monkeypatch.setattr(greenhouse, "pay", lambda tok, jid, india: calls.append((tok, jid, india)) or "₹1,600,000 - ₹2,400,000 /year")
    cache, budget = {"_seen": set()}, [1]
    a, b, c = _gh_job(1), _gh_job(2), _gh_job(3, desc="CTC: 18-24 LPA. Build agents.")
    scan.greenhouse_pay(a, "acme", cache, budget)
    scan.greenhouse_pay(b, "acme", cache, budget)  # budget used up: left for the next scan
    scan.greenhouse_pay(c, "acme", cache, budget)  # the posting already states pay
    assert calls == [("acme", 1, True)]
    assert a.salary_text.startswith("₹1,600,000") and b.salary_text == "" and c.salary_text == ""
    again = _gh_job(1)
    scan.greenhouse_pay(again, "acme", cache, [0])  # cached: no request, no budget needed
    assert again.salary_text == a.salary_text and len(calls) == 1 and "acme:1" in cache["_seen"]


def test_scan_records_greenhouse_pay_and_keeps_cache(tmp_path, monkeypatch):
    boards = {"companies": {
        "Acme": {"status": "mapped", "ats": "greenhouse", "token": "acme", "category": "deep"},
        "Quiet": {"status": "unmapped", "category": "deep", "checkedAt": "2026-10-20T00:00:00Z"},
        "Kiwi": {"status": "unmapped", "category": "saas"},
    }}
    (tmp_path / "boards.json").write_text(json.dumps(boards))
    monkeypatch.setitem(scan.SCOUTS, "greenhouse", lambda tok, name: [_gh_job(7), _gh_job(8, loc="Remote")])
    monkeypatch.setattr(greenhouse, "pay", lambda tok, jid, india: "₹1,600,000 - ₹2,400,000 /year" if jid == 7 else "")
    out = tmp_path / "feed"
    summary = scan.run(tmp_path / "boards.json", out, workers=1, aggregators=False, log=lambda *_: None)
    recs = [json.loads(l) for l in gzip.open(out / "india.jsonl.gz", "rt", encoding="utf-8")]
    by_id = {r["url"].rsplit("/", 1)[1]: r for r in recs}
    assert by_id["7"]["facts"]["salaryHigh"] == 24.0 and by_id["7"]["tags"]["payTier"] == "20+"
    assert by_id["8"]["facts"].get("salaryHigh") is None
    assert summary["greenhousePay"] == {"lookedUp": 2, "withPay": 1}
    assert summary["deepSweep"] == {"checked": 1, "kept": 1}
    assert summary["companies"] == 2  # the swept board with no India roles isn't counted as a company to search
    with gzip.open(out / "greenhouse-pay.json.gz", "rt") as f:
        assert json.load(f) == {"acme:7": "₹1,600,000 - ₹2,400,000 /year", "acme:8": ""}
    names = [r["name"] for r in csv.DictReader((out / "unmapped.csv").open(encoding="utf-8"))]
    assert names == ["Kiwi"]  # swept boards aren't leads for the agent
    # Second scan: both answers come from the cache.
    monkeypatch.setattr(greenhouse, "pay", lambda *a: (_ for _ in ()).throw(AssertionError("no request expected")))
    assert scan.run(tmp_path / "boards.json", out, workers=1, aggregators=False, log=lambda *_: None)["greenhousePay"]["lookedUp"] == 0


# ------------------------------------------------------------------ deep sweep

INVENTORY = {
    "ashby": "name,slug,url\nZeta Labs,zetalabs,https://jobs.ashbyhq.com/zetalabs\nAcme,acme,https://jobs.ashbyhq.com/acme\nBad,a/b,x\n",
    "greenhouse": "name,slug,url\nPostman,postman,https://job-boards.greenhouse.io/postman\nNova AI,nova,https://job-boards.greenhouse.io/nova\n",
}


def test_deep_list_skips_known_boards_and_keeps_its_own(tmp_path):
    rows = deep.fetch(["ashby", "greenhouse", "lever"], get=lambda url: INVENTORY[url.rsplit("/", 1)[1][:-4]], log=lambda *_: None)
    assert [(r["ats"], r["token"]) for r in rows] == [("ashby", "zetalabs"), ("ashby", "acme"), ("greenhouse", "postman"), ("greenhouse", "nova")]
    cache = {"companies": {
        "Postman": {"status": "mapped", "ats": "greenhouse", "token": "postman", "category": "global-india-engineering"},
        "Acme Pvt Ltd": {"status": "unmapped", "category": "saas"},
        "Nova AI": {"status": "mapped", "ats": "greenhouse", "token": "nova", "category": "deep"},
    }}
    todo = deep.build(rows, cache)
    assert [(r["name"], r["token"]) for r in todo] == [("Zeta Labs", "zetalabs"), ("Nova AI", "nova")]
    out = tmp_path / "deep.csv"
    deep.write(todo, out)
    loaded = discover.load_companies(out)
    assert loaded[0]["ats"] == "ashby" and loaded[0]["token"] == "zetalabs" and loaded[0]["slugs"] == [] and loaded[0]["category"] == "deep"
    assert deep.stats(cache) == {"checked": 0, "mapped": 1}


def test_deep_boards_need_developer_roles_open_to_india():
    co = {"name": "Zeta Labs", "category": "deep"}
    india = {"board_name": "Something Else", "locations": ["Bengaluru, Karnataka, India", "New York"], "titles": ["Backend Engineer", "Account Executive"]}
    assert discover.accept(co, india) == (True, "deep:1")  # brand-name mismatch doesn't matter: the inventory named the board
    us_remote = {"locations": ["Remote", "San Francisco"], "titles": ["Software Engineer", "Software Engineer"]}
    assert discover.accept(co, us_remote) == (False, "no-india-dev-roles")  # bare "Remote" is usually the company's own country
    open_remote = {"locations": ["Remote - Worldwide remote"], "titles": ["Full Stack Developer"]}
    assert discover.accept(co, open_remote)[0]
    ashby_secondary = {"locations": ["London"], "titles": ["ML Engineer"], "extra": ["Bengaluru, India"]}
    assert discover.accept(co, ashby_secondary)[0]
    sales = {"locations": ["Bengaluru, India"], "titles": ["Sales Manager"]}
    assert discover.accept(co, sales) == (False, "no-india-dev-roles")
    assert discover.accept(co, {"locations": [], "titles": []}) == (False, "empty")


def test_deep_company_probes_only_its_board_and_waits_three_weeks(monkeypatch):
    seen = []
    monkeypatch.setattr(discover, "probe", lambda ats, slug: seen.append((ats, slug)) or {"locations": ["Austin"], "titles": ["Engineer"]})
    monkeypatch.setattr(discover, "_deadline", [float("inf")])
    res = discover.discover_one({"name": "Zeta Labs", "category": "deep", "slugs": [], "ats": "ashby", "token": "zetalabs"})
    assert seen == [("ashby", "zetalabs")] and res["status"] == "unmapped" and res["retryDays"] == 21
    monkeypatch.setattr(discover, "probe", lambda ats, slug: {"locations": ["Hyderabad, India"], "titles": ["SDE 1"]})
    res = discover.discover_one({"name": "Zeta Labs", "category": "deep", "slugs": [], "ats": "ashby", "token": "zetalabs"})
    assert res["status"] == "mapped" and res["confidence"] == "deep:1" and res["token"] == "zetalabs"
