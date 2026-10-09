"""The sandbox filter script (prompts/agent_filter.py) must decide exactly like `careeros filter-feed`."""

import gzip
import json
import random
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from careeros import extract, feed, scan
from careeros.models import Job, iso

SCRIPT = Path(__file__).resolve().parents[1] / "prompts" / "agent_filter.py"

TITLES = ["AI Engineer", "Senior ML Engineer", "Backend Engineer", "Product Engineer (Remote/US)", "QA Analyst (Mexico, Remote)",
          "Account Executive", "Junior Data Analyst", "Software Engineer (Remote, India)", "Sales Engineer", "Product Designer",
          "Forward Deployed Engineers", "Staff Platform Engineer", "Associate Software Development Engineer (SDE)"]
PLACES = [("Bengaluru, India", ""), ("Hyderabad", "hybrid"), ("Pune, India", "onsite"), ("Remote", "remote"), ("Remote - India", "remote"),
          ("Remote - USA", "remote"), ("San Francisco, CA", "onsite"), ("Remote - APAC", "remote"), ("Anywhere in the World", "remote"),
          ("", ""), ("Chennai; Remote", "remote"), ("London, UK", "hybrid")]
TEXTS = ["Build agents in Python. 0-1 years of experience.", "You have 2+ years of experience shipping ML.", "Freshers welcome to apply.",
         "5+ years building distributed systems. Remote within the US only.", "We build tools for developers.",
         "1+ year with React. Open to candidates anywhere in the world.", "This position has been filled.", "Not a fresher role."]
PAY = ["", "₹5-6 LPA", "₹10-15 LPA", "$100k-$150k"]


def make_feed(path: Path, n: int = 400, seed: int = 7) -> None:
    rnd = random.Random(seed)
    now = datetime.now(timezone.utc)
    with gzip.open(path, "wt", encoding="utf-8") as f:
        for i in range(n):
            loc, mode = rnd.choice(PLACES)
            text = rnd.choice(TEXTS)
            job = Job(company=f"Co{i % 97}", title=rnd.choice(TITLES), url=f"https://jobs.example.com/{i}", source=rnd.choice(["Greenhouse", "Remotive"]),
                      location=loc, work_mode=extract.work_mode(structured=mode, location=loc, text=text), description=text,
                      posted_at=iso(now - timedelta(days=rnd.choice([0.5, 3, 12, 24, 30, 75]))), salary_text=rnd.choice(PAY))
            rec = scan.to_feed(job, {"category": ""}, via=rnd.choice(["careers", "board"]))
            rec["id"] = f"r{i}"
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")


def docs(folder: Path) -> dict:
    return {p.stem: json.loads(p.read_text()) for p in folder.glob("*.json")}


def test_agent_filter_matches_careeros(tmp_path):
    fp = tmp_path / "india.jsonl.gz"
    make_feed(fp)
    known = tmp_path / "known" / "jobs"
    known.mkdir(parents=True)
    (known / "old.json").write_text(json.dumps({"company": "Co1", "title": "AI Engineer", "url": "https://elsewhere.example/1"}))
    for settings in (
        {"maxRequiredYears": 1, "maxPostingAgeDays": 25, "salaryFloorLpa": 7, "targetRoles": [],
         "locations": ["South India (any work mode)", "Rest of India (remote only)", "Remote worldwide (first priority)"]},
        {"maxRequiredYears": 2, "maxPostingAgeDays": 15, "salaryFloorLpa": "", "targetRoles": ["Engineer", "Developer", "Product designer", "Data analyst"],
         "titleExclude": ["Sales"], "locations": ["South India (any work mode)", "Rest of India (remote only)"]},
    ):
        sj = tmp_path / "settings.json"
        sj.write_text(json.dumps({"id": "profile", "data": settings}))
        a, b = tmp_path / "a", tmp_path / "b"
        feed.run(str(fp), feed.settings_from_dashboard(settings), str(tmp_path / "known"), a, max_kept=1000, max_skips=1000, summary={})
        subprocess.run([sys.executable, "-I", str(SCRIPT), str(fp), str(sj), str(tmp_path / "known"), str(b), "1000", "1000"], check=True, capture_output=True)
        ka, kb = docs(a / "kept"), docs(b / "kept")
        assert ka.keys() == kb.keys(), (sorted(ka.keys() - kb.keys())[:5], sorted(kb.keys() - ka.keys())[:5])
        assert {k: d["region"] for k, d in ka.items()} == {k: d["region"] for k, d in kb.items()}
        assert len(ka) > 5  # the generator produces real matches
        sa, sb = docs(a / "skipped"), docs(b / "skipped")
        assert {k: d["skip"]["gate"] for k, d in sa.items()} == {k: d["skip"]["gate"] for k, d in sb.items()}
        for d in kb.values():
            assert d["stage"] == "found" and all(c["passed"] for c in d["checks"])
        for d in (a, b):
            for sub in ("kept", "skipped"):
                for p in (d / sub).glob("*.json"):
                    p.unlink()



def test_agent_filter_finds_gone_and_expired(tmp_path):
    fp = tmp_path / "india.jsonl.gz"
    make_feed(fp, n=20)
    known = tmp_path / "known" / "jobs"
    known.mkdir(parents=True)
    old = (datetime.now(timezone.utc) - timedelta(days=40)).strftime("%Y-%m-%dT%H:%M:%SZ")
    new = (datetime.now(timezone.utc) - timedelta(days=2)).strftime("%Y-%m-%dT%H:%M:%SZ")
    for i, d in {
        "closed": {"company": "A", "title": "AI Engineer", "url": "https://jobs.example.com/gone", "stage": "found", "foundVia": "careers-feed", "postedAt": new},
        "board-down": {"company": "B", "title": "AI Engineer", "url": "https://jobs.example.com/x", "stage": "found", "foundVia": "careers-feed", "postedAt": new},
        "old": {"company": "C", "title": "AI Engineer", "url": "https://x.example/2", "stage": "found", "foundVia": "agent", "postedAt": old},
        "applied": {"company": "D", "title": "AI Engineer", "url": "https://jobs.example.com/y", "stage": "applied", "foundVia": "careers-feed", "postedAt": new},
    }.items():
        (known / f"{i}.json").write_text(json.dumps(d))
    sj, summ = tmp_path / "s.json", tmp_path / "summary.json"
    sj.write_text(json.dumps({"maxPostingAgeDays": 25}))
    summ.write_text(json.dumps({"erroredCompanies": ["B"]}))
    subprocess.run([sys.executable, "-I", str(SCRIPT), str(fp), str(sj), str(tmp_path / "known"), str(tmp_path / "out"), "50", "40", str(summ)], check=True, capture_output=True)
    idx = json.loads((tmp_path / "out" / "index.json").read_text())
    assert idx["gone"] == ["closed"] and idx["expired"] == ["old"]
