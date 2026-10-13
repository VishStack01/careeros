"""The user's apply agent: what to apply to next, one submission per role ever, and reports back."""

from datetime import datetime, timedelta, timezone

import pytest

pytest.importorskip("fastapi")

from conftest import make_pdf  # noqa: E402


def _agent(cloud, c):
    k = cloud.client()
    k.headers["Authorization"] = "Bearer " + c.post("/api/tokens", json={"name": "laptop"}).json()["key"]
    return k


def _job(c, jid, company, stage="found", **extra):
    posted = (datetime.now(timezone.utc) - timedelta(hours=extra.pop("hours", 5))).strftime("%Y-%m-%dT%H:%M:%SZ")
    doc = {"company": company, "title": "AI Engineer", "url": f"https://jobs.example.com/{jid}", "stage": stage, "postedAt": posted,
           "region": extra.pop("region", "remote-global"), "checks": [{"gate": "Role", "passed": True}]}
    doc.update(extra)
    assert c.put(f"/api/d/jobs/{jid}", json=doc).status_code == 200


def test_next_orders_and_limits_roles(cloud):
    c = cloud.user()
    k = _agent(cloud, c)
    c.patch("/api/d/settings/profile", json={"dailyCap": 3, "approvalMode": "auto-when-clear"})
    _job(c, "auto-old", "Old Co", hours=200)
    _job(c, "auto-new", "New Co", hours=2)
    _job(c, "approved", "Approved Co", stage="approved")
    _job(c, "queued", "Queued Co", stage="approved", autoApply="queued", queuedAt="2026-10-01T00:00:00Z")
    _job(c, "waiting", "Waiting Co", stage="approved", autoApply="queued", needsYou="Captcha")
    _job(c, "same-co", "New Co", hours=1, region="south-india")
    _job(c, "failed-check", "Fail Co", checks=[{"gate": "Location", "passed": False}])
    _job(c, "done", "Done Co", stage="applied", appliedAt=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"))
    n = k.get("/api/agent/next").json()
    assert n["dailyCap"] == 3 and n["appliedToday"] == 1 and n["left"] == 2
    assert [r["id"] for r in n["roles"]] == ["queued", "approved"]
    c.patch("/api/d/settings/profile", json={"dailyCap": 10})
    ids = [r["id"] for r in k.get("/api/agent/next?limit=10").json()["roles"]]
    assert ids[:2] == ["queued", "approved"] and "auto-new" in ids and "auto-old" in ids
    assert ids.index("auto-new") < ids.index("auto-old")  # fresher first
    assert "same-co" not in ids and "waiting" not in ids and "failed-check" not in ids and "done" not in ids  # one per company
    c.patch("/api/d/settings/profile", json={"approvalMode": "daily-batch"})
    assert [r["group"] for r in k.get("/api/agent/next?limit=10").json()["roles"]] == ["queued", "approved"]


def test_one_submission_per_role_ever(cloud):
    c = cloud.user()
    k = _agent(cloud, c)
    _job(c, "j1", "Acme", stage="approved", autoApply="queued")
    assert k.post("/api/agent/jobs/j1/finish", json={"confirmed": True}).status_code == 409  # begin first
    assert k.post("/api/agent/jobs/j1/begin").status_code == 200
    r = k.post("/api/agent/jobs/j1/begin")
    assert r.status_code == 409 and r.json()["code"] == "needs_check"  # a crash mid-submit never retries on its own
    r = k.post("/api/agent/jobs/j1/finish", json={"confirmed": True, "confirmation": "Thanks for applying!", "form": "job-boards.greenhouse.io",
                                                 "resumeAsset": "abc", "resumeVersion": "original", "screening": [{"q": "Why us?", "a": "Because."}]})
    assert r.status_code == 200
    d = c.get("/api/d/jobs/j1").json()["data"]
    assert d["stage"] == "applied" and d["appliedVia"] == "careeros" and d["autoApply"] == "done" and d["appliedAt"]
    assert d["application"]["confirmation"] == "Thanks for applying!" and d["resume"]["label"] == "Resume sent"
    assert d["timeline"][-1]["event"].startswith("Applied automatically")
    r = k.post("/api/agent/jobs/j1/begin")
    assert r.status_code == 409 and r.json()["code"] == "already_submitted"
    assert k.get("/api/agent/next").json()["roles"] == []


def test_unconfirmed_submission_waits_for_the_user(cloud):
    c = cloud.user()
    k = _agent(cloud, c)
    _job(c, "j1", "Acme", stage="approved", autoApply="queued")
    k.post("/api/agent/jobs/j1/begin")
    k.post("/api/agent/jobs/j1/finish", json={"confirmed": False, "applyUrl": "https://jobs.example.com/j1/apply"})
    d = c.get("/api/d/jobs/j1").json()["data"]
    assert "no confirmation" in d["needsYou"] and d["applyUrl"].endswith("/apply") and d["stage"] == "approved"
    assert k.post("/api/agent/jobs/j1/begin").json()["code"] == "needs_check"
    # The user checks the site, sees it didn't go through, and presses Try again.
    assert c.post("/api/applications/j1/reset").status_code == 200
    c.patch("/api/d/jobs/j1", json={"needsYou": "", "autoApply": "queued"})
    assert k.post("/api/agent/jobs/j1/begin").status_code == 200


def test_needs_you_closed_fit_runs_and_heartbeat(cloud):
    c = cloud.user()
    k = _agent(cloud, c)
    _job(c, "j1", "Acme", stage="approved")
    _job(c, "j2", "Beta")
    _job(c, "j3", "Gamma")
    assert k.post("/api/agent/jobs/j1/needs-you", json={}).status_code == 400
    k.post("/api/agent/jobs/j1/needs-you", json={"reason": "The form has a captcha.", "applyUrl": "https://x.example/apply"})
    d = c.get("/api/d/jobs/j1").json()["data"]
    assert d["needsYou"] == "The form has a captcha." and d["needsYouAt"] and "captcha" in d["timeline"][-1]["event"]
    k.post("/api/agent/jobs/j2/closed")
    assert c.get("/api/d/jobs/j2").json()["data"]["skip"]["gate"] == "Closed"
    k.post("/api/agent/jobs/j3/fit", json={"decision": "B", "decisionReason": "No React evidence.", "gaps": ["React"], "stage": "applied"})
    d3 = c.get("/api/d/jobs/j3").json()["data"]
    assert d3["decision"] == "B" and d3["gaps"] == ["React"] and d3["stage"] == "found"  # fit can't change the stage
    k.post("/api/agent/heartbeat", json={"device": "Asha's MacBook", "browser": "built-in"})
    runner = c.get("/api/d/settings/applyRunner").json()["data"]
    assert runner["linked"] and runner["device"] == "Asha's MacBook" and runner["lastSeenAt"]
    assert k.post("/api/agent/runs", json={"applied": 1, "needsYou": 1, "summary": "Applied to Acme."}).status_code == 201
    run = [r for r in c.get("/api/c/runs").json()["docs"] if r["data"].get("kind") == "apply"][0]
    assert run["data"]["summary"] == "Applied to Acme." and c.get("/api/d/settings/applyRunner").json()["data"]["lastApplied"] == 1


def test_applicant_resume_text_and_brain(cloud):
    c = cloud.user()
    k = _agent(cloud, c)
    up = c.post("/api/assets?name=cv.pdf", content=make_pdf("Asha Example Python FastAPI"), headers={"Content-Type": "application/pdf"}).json()
    c.put("/api/d/profile/applicant", json={"fullName": "Asha Example", "resume": {"id": up["id"], "name": "cv.pdf"}})
    a = k.get("/api/agent/applicant").json()
    assert a["applicant"]["fullName"] == "Asha Example" and "Python FastAPI" in a["resumeText"] and a["brain"] is None
    assert k.get("/api/agent/next").json()["resume"] == {"id": up["id"], "name": "cv.pdf"}
    assert k.get(f"/_blob/{up['id']}").content.startswith(b"%PDF")
    assert k.post("/api/assets?name=tailored.pdf", content=make_pdf("Tailored"), headers={"Content-Type": "application/pdf"}).status_code == 201
    assert k.post("/api/agent/brain", json={"brain": "nope"}).status_code == 400
    r = k.post("/api/agent/brain", json={"brain": {"claims": [{"id": "c1", "title": "Ticket router"}]}, "status": {"state": "ready", "summary": "1 claim", "counts": {"claims": 1}}})
    assert r.status_code == 200
    assert c.get("/api/d/brain/status").json()["data"]["state"] == "ready"
    assert k.get("/api/agent/applicant").json()["brain"]["claims"][0]["id"] == "c1"
