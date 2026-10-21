"""Tracking: follow-up cadence, reply sorting, stats, calibration, skills gap and warm intros."""

from datetime import datetime, timedelta, timezone

from careeros import analytics, connections, followups, replies

NOW = datetime(2026, 10, 20, 9, 0, tzinfo=timezone.utc)


def iso(d):
    return d.strftime("%Y-%m-%dT%H:%M:%SZ")


def test_followup_cadence():
    applied = {"stage": "applied", "appliedAt": iso(NOW - timedelta(days=8))}
    f = followups.seed(applied, NOW)
    assert [x["kind"] for x in f] == ["applied-1", "applied-2"]
    assert f[0]["due"] == iso(NOW - timedelta(days=1)) and f[1]["due"] == iso(NOW + timedelta(days=6))
    assert followups.seed(dict(applied, followUps=f), NOW) == f  # idempotent
    assert [x["label"] for _, x in followups.due([dict(applied, followUps=f)], NOW)] == ["First follow-up"]
    replied = dict(applied, followUps=f, stage="screen", screenAt=iso(NOW))
    g = followups.seed(replied, NOW)
    assert all(x["done"] and x.get("skipped") for x in g if x["kind"].startswith("applied-"))
    assert any(x["kind"] == "responded" and x["due"] == iso(NOW + timedelta(days=1)) for x in g)
    interview = dict(replied, followUps=g, stage="interview", interviewAt="2026-10-22T10:00:00Z")
    h = followups.seed(interview, NOW)
    assert any(x["label"] == "Thank-you note" and x["due"].startswith("2026-10-23") for x in h)


def test_reply_classification():
    c = replies.classify("Your application to Acme", "Thank you for applying to the AI Engineer role. We have received your application.")
    assert c["kind"] == "confirmation" and c["stage"] is None
    c = replies.classify("Update", "Thank you for your interest. Unfortunately, we have decided to move forward with other candidates.")
    assert c["kind"] == "rejection" and c["stage"] == "rejected" and "other candidates" in c["quote"]
    assert replies.classify("Next steps", "We'd like to invite you to a technical interview. Please pick a slot.")["kind"] == "interview"
    assert replies.classify("Hi", "Your profile stood out. Are you available for a quick call this week?")["kind"] == "recruiter-reply"
    assert replies.classify("Assessment", "Please complete the HackerRank assessment within 3 days.")["kind"] == "assessment"
    assert replies.classify("Offer", "We are pleased to extend an offer for the role.")["kind"] == "offer"
    assert replies.classify("Newsletter", "Our product update for October.")["kind"] == "unclear"
    job = {"stage": "applied", "appliedAt": "2026-10-01T00:00:00Z"}
    assert replies.apply_to_job(job, {"kind": "recruiter-reply", "stage": "screen"}, "2026-10-05T00:00:00Z") == \
        {"stage": "screen", "screenAt": "2026-10-05T00:00:00Z", "firstResponseAt": "2026-10-05T00:00:00Z"}
    assert replies.apply_to_job({"stage": "interview"}, {"kind": "recruiter-reply", "stage": "screen"}, "x") == {}  # never backwards


def _job(i, stage, score=None, region="remote-global", applied_days=10, resp_days=None, **kw):
    j = {"id": f"j{i}", "company": f"Co{i}", "title": "AI Engineer", "stage": stage, "region": region, "foundAt": iso(NOW - timedelta(days=12)),
         "postedAt": iso(NOW - timedelta(days=applied_days, hours=6))}
    if stage not in ("found", "skipped"):
        j["appliedAt"] = iso(NOW - timedelta(days=applied_days))
    if resp_days is not None:
        j["firstResponseAt"] = iso(NOW - timedelta(days=applied_days - resp_days))
    if score is not None:
        j["evaluation"] = {"score": score}
    j.update(kw)
    return j


def test_stats_and_calibration():
    jobs = [_job(1, "screen", 4.6, resp_days=3, screenAt="x"), _job(2, "applied", 4.6), _job(3, "interview", 4.2, region="south-india", resp_days=5),
            _job(4, "rejected", 3.8, resp_days=2), _job(5, "applied"), _job(6, "skipped", skip={"gate": "Experience"}), _job(7, "found")]
    st = analytics.stats(jobs, NOW)
    assert st["applied"] == 5 and st["responded"] == 2 and st["rejected"] == 1 and st["smallSample"]
    assert st["funnel"]["applied"] == 5 and st["funnel"]["interview"] == 1 and st["skipsByGate"] == {"Experience": 1}
    assert st["medianDaysToResponse"] == 3.0 and st["medianHoursPostToApply"] == 6.0
    assert st["byRegion"]["remote-global"]["applied"] == 4
    cal = analytics.calibrate(jobs)
    bands = {b["band"]: b for b in cal["bands"]}
    assert bands["4.5+"]["applied"] == 2 and bands["4.5+"]["responded"] == 1 and bands["4.0-4.4"]["interviews"] == 1
    assert cal["unscored"] == 1 and "early signals" in cal["note"]


def test_skills_gap():
    brain = {"skills": [{"name": "Python", "evidence": ["e1"]}, {"name": "Kubernetes", "evidence": []}]}
    jobs = [{"title": "A", "company": "X", "stage": "found", "skills": ["Python", "Kubernetes", "Go"]},
            {"title": "B", "company": "Y", "stage": "applied", "skills": ["Kubernetes"],
             "evaluation": {"requirements": [{"requirement": "Terraform", "importance": "high", "match": "partial"}]}},
            {"title": "C", "company": "Z", "stage": "skipped", "skills": ["Rust"]}]
    g = {r["skill"]: r for r in analytics.gaps(jobs, brain)}
    assert g["Kubernetes"]["roles"] == 2 and "Python" not in g and "Rust" not in g and g["Terraform"]["partly"] == 1


CSV = """Notes:
"When exporting your connection data, you may notice that some of the email addresses are missing."

First Name,Last Name,URL,Email Address,Company,Position,Connected On
Priya,Raman,https://www.linkedin.com/in/priya,,Razorpay Software Private Limited,Engineering Manager,12 Mar 2025
Arjun,K,https://www.linkedin.com/in/arjun,,"Freshworks, Inc.",Software Engineer,01 Jan 2024
Meera,S,https://www.linkedin.com/in/meera,,Swiggy Instamart,Product Designer,02 Feb 2024
Ravi,T,https://www.linkedin.com/in/ravi,,Zetwerk,Analyst,03 Mar 2024
,,,,,,
"""


def test_warm_intros():
    rows = connections.parse(CSV)
    assert len(rows) == 4 and rows[1]["company"] == "Freshworks, Inc."
    assert [m["name"] for m in connections.matches("Razorpay", rows)] == ["Priya Raman"]
    assert connections.matches("Razorpay", rows)[0]["tier"] == "exact"
    assert connections.matches("Freshworks", rows)[0]["tier"] == "exact"
    assert connections.matches("Swiggy", rows)[0]["tier"] == "strong"
    assert connections.matches("Zeta", rows) == []
    assert connections.parse("not,a,linkedin,file") == []
    assert connections.compact(rows)[0] == ["Priya Raman", "Razorpay Software Private Limited", "Engineering Manager", "https://www.linkedin.com/in/priya"]


def test_dashboard_matching_mirrors_python():
    """The dashboard matches connections in the browser; it must agree with connections.tier."""
    import json
    import shutil
    import subprocess
    from pathlib import Path

    import pytest
    node = shutil.which("node")
    if not node:
        pytest.skip("needs node")
    html = (Path(__file__).resolve().parents[1] / "dashboard" / "app.html").read_text(encoding="utf-8")
    code = html.split("/* ---------- warm intros")[1].split("function uploadConnections")[0]
    code = code.split("\n", 1)[1]  # drop the rest of the comment line
    pairs = [("Razorpay", "Razorpay Software Private Limited"), ("Freshworks", "Freshworks, Inc."), ("Swiggy", "Swiggy Instamart"),
             ("Zeta", "Zetwerk"), ("Acme AI", "Acme Labs"), ("Northwind Labs", "Northwind"), ("Kestrel AI", "Kestrel Analytics"),
             ("Ola", "Ola Electric"), ("Banyan Robotics", "Banyan Tree Hotels"), ("Tata Consultancy Services", "TCS")]
    script = ("const state = {}, arr = x => Array.isArray(x) ? x : [], obj = x => x && typeof x === 'object' ? x : {};\n" + code +
              f"\nconsole.log(JSON.stringify({{t: {json.dumps(pairs)}.map(([a, b]) => coTier(a, b)), rows: parseConnections({json.dumps(CSV)})}}));")
    out = json.loads(subprocess.run([node, "-e", script], capture_output=True, text=True, check=True).stdout)
    assert out["t"] == [connections.tier(a, b) for a, b in pairs]
    assert out["rows"] == connections.compact(connections.parse(CSV))
