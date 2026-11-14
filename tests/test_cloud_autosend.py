"""Automatic recruiter emails from the person's own Gmail: every rule that must hold before a send."""

import base64
from datetime import datetime, timedelta, timezone

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("cryptography")

MONDAY_1030_IST = datetime(2026, 11, 16, 5, 0, tzinfo=timezone.utc)


def _iso(dt):
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


@pytest.fixture
def setup(cloud):
    from careeros.cloud import autosend
    cloud.cfg.google_client_id, cloud.cfg.google_client_secret, cloud.cfg.secrets_key = "gid", "gsecret", "test-secret-0123456789"
    c = cloud.user()
    admin = cloud.user("admin@example.com")
    admin.post("/api/admin/grant", json={"email": "asha@example.com", "plan": "ultra"})
    with cloud.db.tx() as t:
        autosend.save_mailbox(t, cloud.cfg, c.uid, "asha.real@gmail.com", "1//refresh-token")
    c.put("/api/d/profile/applicant", json={"fullName": "Asha Rao", "linkedin": "https://linkedin.com/in/asha"})
    cloud.admin = admin
    return cloud, c


def _role(c, jid, applied, to="priya@northwind.example", source="https://northwind.example/team", stage="applied", outreach_stopped=False, **extra):
    doc = {"company": "Northwind", "title": "AI Engineer", "stage": stage, "appliedAt": _iso(applied),
           "outreach": {"contact": {"name": "Priya Nair", "role": "Recruiter"}, "email": {"to": to, "source": source}, **({"stopped": True} if outreach_stopped else {})}, **extra}
    assert c.put(f"/api/d/jobs/{jid}", json=doc).status_code == 200


def _turn_on(c, follow=False):
    v = c.get("/api/autosend").json()
    c.put("/api/d/settings/outreach", json={"autoSend": True, "followUps": follow, "approvedAt": v["templateHash"]})


def _plan(cloud, uid, now=MONDAY_1030_IST):
    from careeros.cloud import autosend
    with cloud.db.tx() as t:
        u = t.one("SELECT id, name, email, is_admin FROM users WHERE id = ?", (uid,))
        return autosend.plan_user(t, cloud.cfg, u, now)


def test_nothing_is_sent_until_switched_on_and_approved(setup):
    cloud, c = setup
    _role(c, "r1", MONDAY_1030_IST - timedelta(hours=5))
    assert _plan(cloud, c.uid) == []  # off
    c.put("/api/d/settings/outreach", json={"autoSend": True, "approvedAt": "stale"})
    assert _plan(cloud, c.uid) == []  # template not approved
    _turn_on(c)
    rows = _plan(cloud, c.uid)
    assert len(rows) == 1 and rows[0]["to_addr"] == "priya@northwind.example"
    assert "Hi Priya," in rows[0]["body"] and "AI Engineer at Northwind" in rows[0]["subject"] and "Asha Rao" in rows[0]["body"]
    assert "/optout?a=" in rows[0]["body"]  # every email can be opted out of
    assert _plan(cloud, c.uid) == []  # once per role
    # editing the template needs a fresh approval
    c.put("/api/d/settings/outreach", json={"autoSend": True, "approvedAt": c.get("/api/autosend").json()["templateHash"],
                                            "template": {"subject": "Hello {company}"}})
    assert c.get("/api/autosend").json()["approved"] is False


@pytest.mark.parametrize("kw,why", [
    ({"source": ""}, "no public source"),
    ({"to": "priya.northwind@gmail.com"}, "personal mailbox"),
    ({"to": "not-an-address"}, "invalid"),
    ({"stage": "interview"}, "moved on"),
    ({"risk": {"level": "high", "reasons": []}}, "unsafe posting"),
])
def test_roles_that_never_get_an_email(setup, kw, why):
    cloud, c = setup
    _role(c, "r1", MONDAY_1030_IST - timedelta(hours=5), **kw)
    _turn_on(c)
    assert _plan(cloud, c.uid) == [], why


def test_timing_hours_and_plan_limits(setup):
    cloud, c = setup
    _turn_on(c)
    _role(c, "fresh", MONDAY_1030_IST - timedelta(minutes=30))
    _role(c, "old", MONDAY_1030_IST - timedelta(days=5))
    assert _plan(cloud, c.uid) == []  # too soon after applying, and too long ago
    _role(c, "ok", MONDAY_1030_IST - timedelta(hours=4))
    assert _plan(cloud, c.uid, MONDAY_1030_IST + timedelta(hours=10)) == []  # 20:30 IST
    assert _plan(cloud, c.uid, MONDAY_1030_IST - timedelta(days=1)) == []  # Sunday
    assert len(_plan(cloud, c.uid)) == 1
    # Free accounts only draft
    cloud.admin.post("/api/admin/grant", json={"email": "asha@example.com", "plan": "free"})
    _role(c, "ok2", MONDAY_1030_IST - timedelta(hours=4), to="ravi@northwind.example")
    assert _plan(cloud, c.uid) == []


def test_daily_cap_and_one_first_email_per_person(setup):
    cloud, c = setup
    cloud.cfg.pro_ai_credits = 400
    cloud.admin.post("/api/admin/grant", json={"email": "asha@example.com", "plan": "pro"})
    _turn_on(c)
    for i in range(12):
        _role(c, f"r{i}", MONDAY_1030_IST - timedelta(hours=3), to=f"hr{i}@co{i}.example")
    _role(c, "dup", MONDAY_1030_IST - timedelta(hours=3), to="hr0@co0.example")
    rows = _plan(cloud, c.uid)
    assert len(rows) == 10  # Pro: 10 a day
    assert sum(1 for r in rows if r["to_addr"] == "hr0@co0.example") == 1


def test_delivery_threads_follow_ups_and_logs_the_role(setup):
    from careeros.cloud import autosend
    cloud, c = setup
    _turn_on(c, follow=True)
    _role(c, "r1", MONDAY_1030_IST - timedelta(hours=5))
    _plan(cloud, c.uid)
    sent = []

    def send(token, raw, thread_id=""):
        msg = base64.urlsafe_b64decode(raw + "=" * (-len(raw) % 4)).decode()
        sent.append((token, msg, thread_id))
        return {"id": f"m{len(sent)}", "threadId": "t1"}
    tok = lambda refresh, cid, secret: "access-" + refresh  # noqa: E731
    assert autosend.deliver(cloud.db, cloud.cfg, c.uid, send=send, token=tok)["sent"] == 1
    token, msg, thread = sent[0]
    assert token == "access-1//refresh-token" and "To: priya@northwind.example" in msg and "List-Unsubscribe-Post" in msg and thread == ""
    job = c.get("/api/d/jobs/r1").json()["data"]
    assert job["outreach"]["email"]["status"] == "sent" and job["outreach"]["email"]["auto"] is True
    assert "automatically, from your Gmail" in job["timeline"][-1]["event"]

    # day 7: a follow-up in the same thread; nothing earlier
    assert _plan(cloud, c.uid, MONDAY_1030_IST + timedelta(days=4)) == []
    rows = _plan(cloud, c.uid, MONDAY_1030_IST + timedelta(days=7, minutes=5))
    assert [r["kind"] for r in rows] == ["follow1"] and rows[0]["subject"].startswith("Re: ")
    autosend.deliver(cloud.db, cloud.cfg, c.uid, send=send, token=tok)
    assert sent[-1][2] == "t1" and "In-Reply-To:" in sent[-1][1]

    # a reply in the Inbox ends the thread
    c.put("/api/d/inbox/gm-1", json={"from": "priya@northwind.example", "subject": "Re: your application"})
    assert _plan(cloud, c.uid, MONDAY_1030_IST + timedelta(days=14, minutes=5)) == []


def test_stop_cancel_and_opt_out(setup):
    from careeros.cloud import autosend
    cloud, c = setup
    _turn_on(c)
    _role(c, "r1", MONDAY_1030_IST - timedelta(hours=5))
    _role(c, "r2", MONDAY_1030_IST - timedelta(hours=5), to="ravi@acme.example")
    rows = _plan(cloud, c.uid)
    assert len(rows) == 2
    v = c.post(f"/api/autosend/{rows[0]['id']}/cancel").json()
    assert next(s for s in v["sends"] if s["id"] == rows[0]["id"])["status"] == "cancelled"
    assert c.post("/api/autosend/stop/r2").status_code == 200
    assert c.get("/api/d/jobs/r2").json()["data"]["outreach"]["stopped"] is True

    # the recipient opts out from the link: honoured for every Propelo user
    a, s = autosend.optout_token(cloud.cfg, "ravi@acme.example")
    anon = cloud.client()
    assert "ravi@acme.example" in anon.get(f"/optout?a={a}&s={s}").text
    assert anon.post(f"/optout?a={a}&s=0000").status_code == 400
    assert anon.post(f"/optout?a={a}&s={s}").json() == {"ok": True}
    b = cloud.user("bala@example.com")
    with cloud.db.tx() as t:
        autosend.save_mailbox(t, cloud.cfg, b.uid, "bala@gmail.com", "r")
        assert autosend.opted_out(t, "Ravi@Acme.example")


def test_gmail_connect_and_disconnect(setup, monkeypatch):
    from careeros.cloud import mailbox
    cloud, c = setup
    r = c.get("/api/mailbox/google/start", follow_redirects=False)
    assert r.status_code == 303 and "gmail.send" in r.headers["location"] and "access_type=offline" in r.headers["location"]
    state = r.headers["location"].split("state=")[1].split("&")[0]
    monkeypatch.setattr(mailbox, "exchange", lambda *a, **k: {"refresh_token": "1//new", "address": "asha.rao@gmail.com", "scopes": "gmail.send"})
    assert c.get("/api/mailbox/google/callback?code=x&state=wrong", follow_redirects=False).headers["location"] == "/app?mail=state#outreach"
    r = c.get("/api/mailbox/google/start", follow_redirects=False)  # the state is single-use: start again
    state = r.headers["location"].split("state=")[1].split("&")[0]
    r = c.get(f"/api/mailbox/google/callback?code=x&state={state}", follow_redirects=False)
    assert r.headers["location"] == "/app?mail=connected#outreach"
    assert c.get("/api/autosend").json()["mailbox"]["address"] == "asha.rao@gmail.com"
    with cloud.db.tx() as t:
        assert "1//new" not in t.one("SELECT secret FROM mailboxes WHERE user_id = ?", (c.uid,))["secret"]
    revoked = []
    monkeypatch.setattr(mailbox, "revoke", lambda token, post=None: revoked.append(token))
    assert c.delete("/api/mailbox").json()["mailbox"] is None and revoked == ["1//new"]


def test_sending_hours_follow_the_senders_time_zone(setup):
    cloud, c = setup
    _role(c, "r1", MONDAY_1030_IST - timedelta(hours=5))
    v = c.get("/api/autosend").json()
    c.put("/api/d/settings/outreach", json={"autoSend": True, "approvedAt": v["templateHash"], "timezone": "America/New_York"})
    assert c.get("/api/autosend").json()["timezone"] == "America/New_York"
    assert _plan(cloud, c.uid) == []  # 10:30 in India is 00:00 in New York
    assert len(_plan(cloud, c.uid, MONDAY_1030_IST + timedelta(hours=10))) == 1  # 10:00 in New York


def test_odd_documents_never_break_planning(setup):
    cloud, c = setup
    _turn_on(c)
    c.put("/api/d/jobs/odd", json={"company": "X", "title": "Y", "stage": "applied", "appliedAt": _iso(MONDAY_1030_IST - timedelta(hours=5)),
                                   "evidence": ["not a dict"], "outreach": {"email": "not a dict", "contact": "nobody"}})
    _role(c, "stopped", MONDAY_1030_IST - timedelta(hours=5), to="a@b.example", outreach_stopped=True)
    assert _plan(cloud, c.uid) == []  # the odd one is skipped, and Stop before the first email holds


def test_bad_subjects_and_addresses_never_jam_the_queue(setup):
    from careeros.cloud import autosend
    cloud, c = setup
    _turn_on(c)
    assert not autosend.EMAIL.match("priya@northwind.example\n")
    _role(c, "r1", MONDAY_1030_IST - timedelta(hours=5), to="priya@northwind.example")
    c.patch("/api/d/jobs/r1", json={"outreach": {"contact": {"name": "Priya"}, "email": {"to": "priya@northwind.example", "source": "https://northwind.example/team",
                                                                                         "status": "drafted", "subject": "Hello\nthere", "body": "Hi Priya"}}})
    _role(c, "r2", MONDAY_1030_IST - timedelta(hours=5), to="ravi@acme.example")
    rows = _plan(cloud, c.uid)
    assert sorted(r["subject"] for r in rows)[0] == "Hello there"
    with cloud.db.tx() as t:  # a row that can't be built (simulated) fails alone; the rest still go
        t.execute("UPDATE outreach_sends SET to_addr = ? WHERE job_id = 'r1'", ("bad\r\naddress@x.example",))
    res = autosend.deliver(cloud.db, cloud.cfg, c.uid, send=lambda tok, raw, thread_id="": {"id": "m", "threadId": "t"}, token=lambda *a: "tok")
    assert res == {"sent": 1, "failed": 1}
