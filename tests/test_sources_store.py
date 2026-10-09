import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from careeros import pipeline
from careeros.dedupe import canonical_url, fingerprint
from careeros.settings import Settings
from careeros.sources import ashby, greenhouse, lever
from careeros.store import AlreadySubmitted, NeedsHumanCheck, Paused, Store

FIX = Path(__file__).parent / "fixtures"
NOW = datetime(2026, 10, 9, 6, 0, tzinfo=timezone.utc)


def load(name):
    return json.loads((FIX / name).read_text())


def test_greenhouse_normalize():
    jobs = [greenhouse.normalize(j, "Example Labs") for j in load("greenhouse.json")["jobs"]]
    first = jobs[0]
    assert first.title == "AI Engineer, Agents"
    assert "0-1 years" in first.description and "<li>" not in first.description
    assert first.location == "Bengaluru, India"


def test_lever_normalize_salary_and_remote():
    job = lever.normalize(load("lever.json")[0], "Sample Corp")
    assert job.work_mode == "remote"
    assert "1+ year" in job.description
    assert "8,00,000" in job.salary_text or "800,000" in job.salary_text


def test_ashby_normalize():
    jobs = [ashby.normalize(j, "Demo Co") for j in load("ashby.json")["jobs"]]
    assert jobs[0].work_mode == "remote" and jobs[1].work_mode == "onsite"


def test_dedupe_keys():
    assert canonical_url("https://Job-Boards.greenhouse.io/x/jobs/1?gh_src=abc&utm_source=li") == "https://job-boards.greenhouse.io/x/jobs/1"
    assert fingerprint("Example Labs Pvt Ltd", "AI Engineer (Remote)") == fingerprint("example labs", "AI Engineer")


def test_pipeline_end_to_end(tmp_path, monkeypatch):
    monkeypatch.setitem(pipeline.SCOUTS, "greenhouse", lambda token, company=None: [greenhouse.normalize(j, company) for j in load("greenhouse.json")["jobs"]])
    monkeypatch.setitem(pipeline.SCOUTS, "lever", lambda token, company=None: [lever.normalize(j, company) for j in load("lever.json")])
    monkeypatch.setitem(pipeline.SCOUTS, "ashby", lambda token, company=None: [ashby.normalize(j, company) for j in load("ashby.json")["jobs"]])
    store = Store(tmp_path / "t.db")
    boards = [
        {"ats": "greenhouse", "token": "examplelabs", "company": "Example Labs"},
        {"ats": "lever", "token": "samplecorp", "company": "Sample Corp"},
        {"ats": "ashby", "token": "demo-co", "company": "Demo Co"},
    ]
    rep = pipeline.run(store, Settings(), boards, now=NOW)
    jobs = {d["data"]["title"]: d["data"] for d in store.list("jobs")}
    assert jobs["AI Engineer, Agents"]["stage"] == "found"  # nice-to-have years ignored
    assert jobs["Junior AI Automation Engineer"]["region"] == "remote-india"
    assert jobs["Applied AI Engineer (New Grad)"]["region"] == "remote-global"
    assert jobs["Senior ML Engineer"]["stage"] == "skipped"
    assert "Account Executive" not in jobs  # unrelated listings aren't logged
    assert rep.kept[0]["region"] == "remote-global"  # worldwide remote sorts first
    # A second run finds nothing new.
    rep2 = pipeline.run(store, Settings(), boards, now=NOW)
    assert rep2.added == 0 and rep2.known >= 3


def test_submit_state_machine(tmp_path):
    store = Store(tmp_path / "t.db")
    job = {"company": "Demo Co", "title": "Applied AI Engineer", "url": "https://jobs.ashbyhq.com/demo-co/f00d-1"}
    key = store.begin_submit("demo", job)
    # A crash mid-submit must block blind retries.
    with pytest.raises(NeedsHumanCheck):
        store.begin_submit("demo", job)
    store.finish_submit(key, True, {"job_id": "demo"})
    with pytest.raises(AlreadySubmitted):
        store.begin_submit("demo", job)
    assert store.applied_recently("Demo Co")
    store.set_flag("paused", True)
    with pytest.raises(Paused):
        store.begin_submit("other", {"company": "X", "title": "Y", "url": "https://x"})


def test_doc_merge_and_delete(tmp_path):
    store = Store(tmp_path / "t.db")
    store.set("jobs", "a", {"stage": "found", "brief": {"about": "x", "team": "y"}})
    v = store.update("jobs", "a", {"brief": {"team": "z"}, "stage": {"__delete__": True}})
    doc = store.get("jobs", "a")
    assert doc["version"] == v == 2
    assert doc["data"] == {"brief": {"about": "x", "team": "z"}}
    with pytest.raises(ValueError):
        store.update("jobs", "a", {"x": 1}, if_version=1)
