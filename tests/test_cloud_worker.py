"""The worker: feed ingestion (fail-closed), per-user matching and the durable task queue."""

import json
from datetime import timedelta

import pytest

pytest.importorskip("fastapi")

from conftest import feed_record, write_feed  # noqa: E402


def _worker(cloud, wid="w1"):
    from careeros.cloud.worker import Worker
    return Worker(cloud.cfg, cloud.db, cloud.app.state.mailer, worker_id=wid)


def test_ingest_then_match_each_user(cloud, tmp_path):
    from careeros.cloud.ingest import feed_state
    write_feed(tmp_path / "feed", [feed_record(i) for i in range(30)]
               + [feed_record(100, exp=3)]  # asks for 3 years: a near-miss
               + [feed_record(101, title="Sales Manager")])  # not a target role
    a = cloud.user("asha@example.com")
    b = cloud.user("bala@example.com")
    b.patch("/api/d/settings/profile", json={"titleExclude": ["Engineer 1"]})
    w = _worker(cloud)
    w.drain()
    with cloud.db.tx() as c:
        assert c.scalar("SELECT COUNT(*) AS n FROM jobs WHERE active = 1") == 32
        assert feed_state(c)["records"] == 32
    jobs_a = {d["id"]: d["data"] for d in a.get("/api/c/jobs").json()["docs"]}
    kept = [i for i, d in jobs_a.items() if d["stage"] == "found"]
    assert len(kept) == 30 and all(jobs_a[i]["checks"] for i in kept)
    assert jobs_a["co20-ai-engineer-100"]["stage"] == "skipped" and "Experience" in jobs_a["co20-ai-engineer-100"]["skip"]["gate"]
    assert "co21-ai-engineer-101" not in jobs_a
    jobs_b = {d["id"] for d in b.get("/api/c/jobs").json()["docs"]}
    assert len(jobs_b) < len(jobs_a)  # b's own filters
    run = [r["data"] for r in a.get("/api/c/runs").json()["docs"]][0]
    assert run["kind"] == "search" and run["added"] == 30 and "best remote-worldwide" in run["summary"]
    assert a.get("/api/d/settings/profile").json()["data"]["coverage"]["inventory"] == 32
    assert a.get("/api/me").json()["feed"]["inventory"] == 32
    # A second hourly run with no new feed changes nothing.
    with cloud.db.tx() as c:
        c.execute("UPDATE feed_state SET value = ? WHERE key = 'next_ingest_at'", ("2000-01-01T00:00:00Z",))
    w.drain()
    assert len(a.get("/api/c/jobs").json()["docs"]) == len(jobs_a)


def test_closed_roles_leave_the_pipeline_but_not_when_a_board_errored(cloud, tmp_path):
    records = [feed_record(i) for i in range(10)]
    write_feed(tmp_path / "feed", records)
    a = cloud.user()
    w = _worker(cloud)
    w.drain()
    a.patch("/api/d/jobs/co3-ai-engineer-3", json={"stage": "approved", "autoApply": "queued"})
    # Next scan: role 1 is gone (its board was read), role 2's board errored, role 3 is gone but the user queued it.
    write_feed(tmp_path / "feed", [r for r in records if r["id"] not in ("co1-ai-engineer-1", "co2-ai-engineer-2", "co3-ai-engineer-3")],
               generated="2099-01-01T00:00:00Z", errored=["Company 2"])
    from careeros.cloud.ingest import ingest
    assert ingest(cloud.db, cloud.cfg.feed_url, log=lambda *_: None)["closed"] == 2
    from careeros.cloud.matching import match_user
    match_user(cloud.db, a.uid, log=lambda *_: None)
    jobs = {d["id"]: d["data"] for d in a.get("/api/c/jobs").json()["docs"]}
    assert jobs["co1-ai-engineer-1"]["stage"] == "skipped" and jobs["co1-ai-engineer-1"]["skip"]["gate"] == "Closed"
    assert jobs["co2-ai-engineer-2"]["stage"] == "found"
    assert jobs["co3-ai-engineer-3"]["stage"] == "approved"  # your queue is yours


def test_ingest_fails_closed(cloud, tmp_path):
    from careeros.cloud.ingest import IngestError, ingest
    with pytest.raises(IngestError):
        ingest(cloud.db, str(tmp_path / "missing"), log=lambda *_: None)
    write_feed(tmp_path / "feed", [feed_record(i) for i in range(300)])
    ingest(cloud.db, cloud.cfg.feed_url, log=lambda *_: None)
    write_feed(tmp_path / "feed", [feed_record(i) for i in range(100)], generated="2099-01-01T00:00:00Z")
    with pytest.raises(IngestError, match="shrank"):
        ingest(cloud.db, cloud.cfg.feed_url, log=lambda *_: None)
    with cloud.db.tx() as c:
        assert c.scalar("SELECT COUNT(*) AS n FROM jobs WHERE active = 1") == 300
    assert ingest(cloud.db, cloud.cfg.feed_url, force=True, log=lambda *_: None)["closed"] == 200
    (tmp_path / "feed" / "summary.json").unlink()
    with pytest.raises(IngestError, match="summary"):
        ingest(cloud.db, cloud.cfg.feed_url, log=lambda *_: None)


def test_queue_dedupe_retry_and_leases(cloud):
    from careeros.cloud import repo
    from careeros.cloud.db import now_iso
    w1, w2 = _worker(cloud, "w1"), _worker(cloud, "w2")
    with cloud.db.tx() as c:
        c.execute("DELETE FROM tasks")
        c.execute("INSERT INTO feed_state(key, value, updated_at) VALUES ('next_ingest_at', '2999-01-01', 'x'), ('next_cleanup_at', '2999-01-01', 'x')")
        assert repo.enqueue(c, "send_email", {"to": "a@example.com", "subject": "s", "text": "t"}, dedupe_key="mail:1")
        assert not repo.enqueue(c, "send_email", {"to": "a@example.com", "subject": "s", "text": "t"}, dedupe_key="mail:1")
        assert repo.enqueue(c, "nonsense", dedupe_key="bad", max_attempts=2)
    t = w1.claim()
    assert t["status"] == "running" and t["locked_by"] == "w1" and t["attempts"] == 1
    assert w2.claim()["kind"] != t["kind"]  # the second worker skips the leased task
    assert w2.claim() is None
    # w1 dies: once the lease runs out, another worker takes the task over.
    with cloud.db.tx() as c:
        c.execute("UPDATE tasks SET locked_until = ? WHERE id = ?", (now_iso(timedelta(minutes=-1)), t["id"]))
    again = w2.claim()
    assert again["id"] == t["id"] and again["locked_by"] == "w2" and again["attempts"] == 2
    w2.run(again)
    with cloud.db.tx() as c:
        rows = {r["kind"]: r for r in c.all("SELECT kind, status, payload, attempts, last_error, run_after FROM tasks")}
    assert rows["send_email"]["status"] == "done" and rows["send_email"]["payload"] == "{}"  # the link isn't kept
    assert rows["nonsense"]["status"] == "running"
    bad = [r for r in [w1.claim()] if r] or []
    with cloud.db.tx() as c:
        c.execute("UPDATE tasks SET locked_until = ?, status = 'running' WHERE kind = 'nonsense'", (now_iso(timedelta(minutes=-1)),))
    task = w1.claim()
    w1.run(task)
    with cloud.db.tx() as c:
        r = c.one("SELECT status, attempts, last_error FROM tasks WHERE kind = 'nonsense'")
    assert r["status"] == "failed" and "unknown task" in r["last_error"] and not bad
    with cloud.db.tx() as c:  # once finished, the same dedupe key can be queued again
        assert repo.enqueue(c, "send_email", {"to": "a@example.com", "subject": "s", "text": "t"}, dedupe_key="mail:1")


def test_failed_task_backs_off(cloud):
    from careeros.cloud import repo
    from careeros.cloud.db import now_iso
    w = _worker(cloud)
    with cloud.db.tx() as c:
        c.execute("DELETE FROM tasks")
        c.execute("INSERT INTO feed_state(key, value, updated_at) VALUES ('next_ingest_at', '2999-01-01', 'x'), ('next_cleanup_at', '2999-01-01', 'x')")
        repo.enqueue(c, "ingest", dedupe_key="ingest", max_attempts=3)  # the feed folder doesn't exist: fails closed
    w.tick()
    with cloud.db.tx() as c:
        r = c.one("SELECT status, attempts, run_after, last_error FROM tasks WHERE kind = 'ingest'")
    assert r["status"] == "queued" and r["attempts"] == 1 and r["run_after"] > now_iso(timedelta(minutes=1)) and "empty" in r["last_error"]
    assert w.claim() is None  # not due yet


def test_scheduler_and_cleanup(cloud):
    from careeros.cloud.worker import cleanup
    w = _worker(cloud)
    with cloud.db.tx() as c:
        c.execute("DELETE FROM tasks")
    w.schedule()
    w.schedule()
    with cloud.db.tx() as c:
        kinds = sorted(r["kind"] for r in c.all("SELECT kind FROM tasks"))
    assert kinds == ["cleanup", "ingest"]  # once each, however often the scheduler ticks
    out = cleanup(cloud.db)
    assert set(out) == {"sessions", "links", "rate", "tasks", "jobs", "audit"}
    assert json.dumps(out)


def test_concurrent_workers_claim_each_task_once(cloud):
    import threading

    from careeros.cloud import repo
    with cloud.db.tx() as c:
        c.execute("DELETE FROM tasks")
        c.execute("INSERT INTO feed_state(key, value, updated_at) VALUES ('next_ingest_at', '2999-01-01', 'x'), ('next_cleanup_at', '2999-01-01', 'x')")
        for i in range(60):
            repo.enqueue(c, "cleanup", dedupe_key=f"t{i}")
    claimed, lock = [], threading.Lock()

    def work(wid):
        w = _worker(cloud, wid)
        while True:
            t = w.claim()
            if not t:
                return
            with lock:
                claimed.append(t["id"])
    threads = [threading.Thread(target=work, args=(f"w{i}",)) for i in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert len(claimed) == 60 and len(set(claimed)) == 60


def test_ingest_drops_implausible_pay(cloud, tmp_path):
    import json as _json

    from careeros.cloud.ingest import ingest
    r = feed_record(1)
    r["facts"].update(salaryLow=687280.0, salaryHigh=687280.0, salaryQuote="We've raised $781M")
    write_feed(tmp_path / "feed", [r, feed_record(2)])
    ingest(cloud.db, cloud.cfg.feed_url, log=lambda *_: None)
    with cloud.db.tx() as c:
        facts = {row["id"]: _json.loads(row["record"])["facts"] for row in c.all("SELECT id, record FROM jobs")}
    assert "salaryHigh" not in facts[r["id"]] and facts[feed_record(2)["id"]]["salaryHigh"] == 14.0
