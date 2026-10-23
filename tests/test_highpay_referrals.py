"""High-pay reach (public pay data, Workday, Amazon, honest board guesses), the referral finder and LinkedIn sign-in."""

import json
from datetime import datetime, timezone

import pytest

from careeros import discover, feed, paydata, referrals, scan
from careeros.gates import gate_pay
from careeros.models import Job
from careeros.settings import Settings
from careeros.sources import amazon, workday


# ------------------------------------------------------------------ public pay data

def test_pay_band_lookup_and_aliases():
    assert paydata.band("DE Shaw & Co")["low"] == 62
    assert paydata.band("J.P. Morgan")["low"] == 12
    assert paydata.band("Some Startup") is None
    assert paydata.describe(paydata.band("Tower Research Capital")).startswith("25–90 LPA for freshers")


def _job(company, salary="", facts=None):
    return Job(company=company, title="Software Engineer", url="https://x.example/1", source="Greenhouse",
               description="Build systems.", salary_text=salary, raw={"facts": facts} if facts is not None else {})


def test_pay_gate_uses_public_data_only_when_pay_isnt_stated():
    s = Settings(salary_floor_lpa=15, require_stated_pay=True)
    tower = {"payBand": paydata.band("Tower Research Capital")}
    c, _ = gate_pay(_job("Tower Research Capital", facts=tower), s)
    assert c.passed and c.value.startswith("Not stated; public data: 25–90 LPA")
    jpm = {"payBand": paydata.band("JPMorgan Chase")}
    c, _ = gate_pay(_job("JPMorgan Chase", facts=jpm), s)  # low end 12 < 15: not enough evidence
    assert not c.passed and "Public data for freshers here: 12–18 LPA" in c.value
    c, _ = gate_pay(_job("Unknown Co", facts={}), s)
    assert not c.passed
    c, _ = gate_pay(_job("Tower Research Capital", salary="₹8-10 LPA", facts=tower), s)  # the posting's own figure wins
    assert not c.passed and "below your 15 LPA floor" in c.value
    c, _ = gate_pay(_job("Unknown Co", facts={}), Settings(salary_floor_lpa=15))
    assert c.passed and c.value == "Not stated"


def test_feed_record_carries_band_and_sorts_it_first():
    now = datetime.now(timezone.utc)
    recs = []
    for i, (co, sal) in enumerate([("Co A", ""), ("Tower Research Capital", ""), ("Co B", "₹16-18 LPA")]):
        j = Job(company=co, title="Software Engineer", url=f"https://x.example/{i}", source="Greenhouse", location="Bengaluru, India",
                description="0-1 years. Build systems.", posted_at=now.strftime("%Y-%m-%dT%H:%M:%SZ"), salary_text=sal)
        r = scan.to_feed(j, {"category": ""})
        r["id"] = f"r{i}"
        recs.append(r)
    assert recs[1]["facts"]["payBand"]["low"] == 25 and "payBand" not in recs[0]["facts"]
    s = feed.settings_from_dashboard({"salaryFloorLpa": 15, "requireStatedPay": True, "targetRoles": ["Engineer"]})
    res = feed.match(recs, s, [], now=now)
    kept = [d["company"] for _, d in res["kept"]]
    assert kept == ["Tower Research Capital", "Co B"]  # public-data 20 LPA+ first; "Co A" states nothing
    assert res["kept"][0][1]["payBand"]["source"]
    skipped = {d["company"]: d["skip"] for _, d in res["skipped"]}
    assert skipped["Co A"]["wouldChange"] == "Allowing roles that don't state pay."


def test_rest_of_india_any_wins_when_both_are_ticked():
    s = feed.settings_from_dashboard({"locations": ["Rest of India (remote only)", "Rest of India (any work mode)"]})
    assert s.location.rest_of_india == "any"


# ------------------------------------------------------------------ Workday and Amazon

WD_LIST = {"total": 2, "facets": [{"facetParameter": "locationMainGroup", "values": [
    {"facetParameter": "locationCountry", "values": [{"descriptor": "United States", "id": "us1"}, {"descriptor": "India", "id": "in1"}]}]}],
    "jobPostings": [{"title": "Software Engineer", "externalPath": "/job/Bengaluru/Software-Engineer_JR1", "locationsText": "Bengaluru, India",
                     "postedOn": "Posted 3 Days Ago", "bulletFields": ["JR1"]},
                    {"title": "Payroll Specialist", "externalPath": "/job/Pune/Payroll_JR2", "locationsText": "Pune, India", "postedOn": "Posted Today"}]}
WD_DETAIL = {"jobPostingInfo": {"title": "Software Engineer", "jobDescription": "<p>0-1 years. Build GPU tools in C++.</p>",
                                "location": "Bengaluru, India", "startDate": "2026-10-20", "externalUrl": "https://nvidia.wd5.myworkdayjobs.com/en-US/X/job/1"}}


def test_workday_reads_india_through_the_country_facet(monkeypatch):
    posts, gets = [], []
    monkeypatch.setattr(workday, "post_json", lambda url, body, **kw: posts.append((url, body)) or WD_LIST)
    monkeypatch.setattr(workday, "get_json", lambda url, **kw: gets.append(url) or WD_DETAIL)
    jobs = workday.fetch("nvidia/wd5/NVIDIAExternalCareerSite", "NVIDIA")
    assert posts[0][0] == "https://nvidia.wd5.myworkdayjobs.com/wday/cxs/nvidia/NVIDIAExternalCareerSite/jobs"
    assert posts[1][1]["appliedFacets"] == {"locationCountry": ["in1"]} and posts[1][1]["searchText"] == ""
    assert gets == ["https://nvidia.wd5.myworkdayjobs.com/wday/cxs/nvidia/NVIDIAExternalCareerSite/job/Bengaluru/Software-Engineer_JR1"]  # tech titles only
    se, payroll = jobs
    assert se.posted_at == "2026-10-20T00:00:00Z" and "GPU tools" in se.description and se.url.endswith("/job/1")
    assert payroll.description == "" and payroll.url == "https://nvidia.wd5.myworkdayjobs.com/NVIDIAExternalCareerSite/job/Pune/Payroll_JR2"
    assert workday.token_from_url("https://adobe.wd5.myworkdayjobs.com/en-US/external_experienced/job/x") == "adobe/wd5/external_experienced"
    with pytest.raises(ValueError):
        workday.parse_token("adobe/external")


def test_amazon_reader_pages_and_parses(monkeypatch):
    calls = []
    hit = {"title": "SDE I, Alexa", "job_path": "/en/jobs/123/sde-i", "normalized_location": "Bengaluru, KA, IND",
           "posted_date": "October 20, 2026", "description": "Build things.", "basic_qualifications": "- 1+ years of non-internship professional software development experience",
           "id_icims": "123"}
    monkeypatch.setattr(amazon, "get_json", lambda url, **kw: calls.append(url) or {"jobs": [hit] if len(calls) == 1 else []})
    jobs = amazon.fetch("IND")
    assert len(jobs) == 1 and jobs[0].url == "https://www.amazon.jobs/en/jobs/123/sde-i" and jobs[0].posted_at == "2026-10-20T00:00:00Z"
    assert "normalized_country_code%5B%5D=IND" in calls[0] and "Basic qualifications" in jobs[0].description


def test_discover_respects_custom_sites_and_listed_boards(monkeypatch):
    monkeypatch.setattr(discover, "_deadline", [float("inf")])
    seen = []
    monkeypatch.setattr(discover, "probe", lambda ats, slug: seen.append((ats, slug)) or {"locations": ["Hyderabad, India"], "titles": ["Engineer"]})
    assert discover.discover_one({"name": "Google", "category": "global-india-engineering", "slugs": ["google"], "ats": "custom"})["custom"]
    assert seen == []  # never guesses a slug for a company with its own career site
    res = discover.discover_one({"name": "NVIDIA", "category": "high-pay", "slugs": [], "ats": "workday", "token": "nvidia/wd5/x"})
    assert res["status"] == "mapped" and res["confidence"] == "listed"
    # A slug guess with no board name and no India or remote roles is no longer accepted for global companies.
    ok, conf = discover.accept({"name": "Google", "category": "global-india-engineering"}, {"board_name": "", "locations": ["Austin, TX"]})
    assert not ok


def test_discover_rechecks_when_the_list_names_a_new_board(tmp_path, monkeypatch):
    csv_path = tmp_path / "c.csv"
    csv_path.write_text("name,category,city,website,slugs,ats,token,source\nAmazon,global-india-engineering,,,,amazon,IND,x\nGoogle,global-india-engineering,,,google,custom,,x\n")
    cache = {"companies": {"Amazon": {"status": "mapped", "ats": "breezy", "token": "amazon", "checkedAt": "2026-10-20T00:00:00Z"},
                           "Google": {"status": "mapped", "ats": "recruitee", "token": "google", "checkedAt": "2026-10-20T00:00:00Z"}}}
    (tmp_path / "b.json").write_text(json.dumps(cache))
    monkeypatch.setattr(discover, "probe", lambda ats, slug: {"board_name": "Amazon", "locations": ["Bengaluru, India"], "titles": ["SDE"]} if ats == "amazon" else None)
    out = discover.run(csv_path, tmp_path / "b.json", workers=1, log=lambda *_: None)["companies"]
    assert (out["Amazon"]["ats"], out["Amazon"]["token"]) == ("amazon", "IND")
    assert out["Google"]["status"] == "unmapped" and out["Google"]["custom"]


# ------------------------------------------------------------------ referral finder

ME = {"fullName": "Asha Example", "college": "GITAM University", "city": "Bengaluru", "currentTitle": "AI Product Designer", "currentCompany": "Kiwi"}


def test_referral_ranking_prefers_alumni_engineers_and_connections():
    people = [{"name": "Ravi A", "headline": "SDE 2 at Razorpay | GITAM University", "url": "https://linkedin.com/in/a", "location": "Bengaluru", "degree": "2nd"},
              {"name": "Meera B", "headline": "Engineering Manager at Razorpay", "url": "https://linkedin.com/in/b"},
              {"name": "Kabir C", "headline": "Backend Engineer at Swiggy | ex-Razorpay", "url": "https://linkedin.com/in/c"},
              {"name": "Dev D", "headline": "Co-founder & CEO at Razorpay", "url": "https://linkedin.com/in/d"}]
    conns = [{"name": "Tara E", "company": "Razorpay Software", "position": "Software Engineer", "url": "https://linkedin.com/in/e", "connectedOn": "1 Jan 2026"}]
    ranked = referrals.rank("Razorpay", "SDE 1", ME, conns, people)
    names = [p["name"] for p in ranked]
    assert names[0] == "Ravi A" and "Kabir C" not in names and names.index("Dev D") == len(names) - 1
    tara = next(p for p in ranked if p["name"] == "Tara E")
    assert "Already a connection" in tara["why"] and tara["via"] == "Your connections"


def test_referral_links_and_drafts_stay_honest():
    plan = referrals.plan("Razorpay", "SDE 1", ME, [], [{"name": "Ravi A", "headline": "SDE at Razorpay | GITAM University"}], "https://jobs.example/1")
    urls = [l["url"] for l in plan["searchLinks"]]
    assert all(u.startswith(("https://www.linkedin.com/search/results/people/", "https://www.google.com/search")) for u in urls)
    assert any("gitam" in u.lower() for u in urls) and any("network=%5B%22S%22%5D" in u for u in urls)
    note = plan["drafts"]["connectionNote"]
    assert len(note) <= referrals.NOTE_LIMIT and note.startswith("Hi Ravi") and "Fellow GITAM University grad" in note
    assert "https://jobs.example/1" in plan["drafts"]["referralAsk"] and "Asha Example" in plan["drafts"]["referralAsk"]


def test_referrals_cli(tmp_path, capsys):
    from careeros.cli import main
    (tmp_path / "Connections.csv").write_text("Notes:\n\nFirst Name,Last Name,URL,Email Address,Company,Position,Connected On\n"
                                              "Tara,E,https://linkedin.com/in/e,,Razorpay,Software Engineer,01 Jan 2026\n")
    (tmp_path / "me.json").write_text(json.dumps({"data": ME}))
    main(["referrals", "--company", "Razorpay", "--title", "SDE 1", "--connections", str(tmp_path / "Connections.csv"),
          "--applicant", str(tmp_path / "me.json"), "--json"])
    out = json.loads(capsys.readouterr().out)
    assert out["people"][0]["name"] == "Tara E" and out["drafts"]["connectionNote"].startswith("Hi Tara")


# ------------------------------------------------------------------ Sign in with LinkedIn

def test_linkedin_sign_in(cloud, monkeypatch):
    from careeros.cloud import linkedin
    c = cloud.client()
    assert c.get("/api/auth/providers").json() == {"linkedin": False}
    assert c.get("/api/auth/linkedin/start", follow_redirects=False).status_code == 404
    cloud.cfg.linkedin_client_id, cloud.cfg.linkedin_client_secret = "cid", "secret"
    r = c.get("/api/auth/linkedin/start", follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"].startswith("https://www.linkedin.com/oauth/v2/authorization?")
    assert "scope=openid+profile+email" in r.headers["location"]
    state = r.headers["location"].split("state=")[1].split("&")[0]
    # A forged state is refused.
    r = c.get("/api/auth/linkedin/callback?code=abc&state=wrong", follow_redirects=False)
    assert r.status_code == 303 and "linkedin_state" in r.headers["location"]
    r = c.get("/api/auth/linkedin/start", follow_redirects=False)
    state = r.headers["location"].split("state=")[1].split("&")[0]
    monkeypatch.setattr(linkedin, "exchange", lambda code, redirect, cid, secret: "tok" if code == "abc" and cid == "cid" else None)
    monkeypatch.setattr(linkedin, "userinfo", lambda tok: {"sub": "x1", "name": "Asha Example", "email": "Asha@Example.com", "email_verified": True})
    r = c.get(f"/api/auth/linkedin/callback?code=abc&state={state}", follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/app"
    me = c.get("/api/me").json()
    assert me["email"] == "asha@example.com" and me["emailVerified"] and me["name"] == "Asha Example"
    # The account has no password: password sign-in fails until one is set through "Forgot password".
    assert cloud.client().post("/api/auth/login", json={"email": "asha@example.com", "password": "!linkedin"}).status_code == 401
    # An unconfirmed LinkedIn email is not accepted.
    c2 = cloud.client()
    state = c2.get("/api/auth/linkedin/start", follow_redirects=False).headers["location"].split("state=")[1].split("&")[0]
    monkeypatch.setattr(linkedin, "userinfo", lambda tok: {"sub": "x2", "name": "B", "email": "b@example.com", "email_verified": False})
    r = c2.get(f"/api/auth/linkedin/callback?code=abc&state={state}", follow_redirects=False)
    assert "linkedin_no_email" in r.headers["location"] and c2.get("/api/me").status_code == 401
