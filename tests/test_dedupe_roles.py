"""One role, one record: reposts, location suffixes, legal names and abbreviations don't make a new role."""

import gzip
import json
import subprocess
import sys
from pathlib import Path

from careeros.dedupe import fingerprint, title_key

SCRIPT = Path(__file__).resolve().parents[1] / "prompts" / "agent_filter.py"


def test_same_role_written_differently_matches():
    same = [("Amazon", "SDE I FTC", "Amazon", "Software Development Engineer I FTC"),
            ("Amazon", "SDE-1", "Amazon", "Software Development Engineer I"),
            ("Tether", "Mobile Engineer - React Native (100% Remote)", "Tether Operations Limited", "Mobile Engineer - React Native (100% Remote) - Worldwide"),
            ("Speechify", "Software Engineer, AI Data", "Speechify", "Software Engineer, AI Data - Galway, Ireland"),
            ("Acme GmbH", "Backend Engineer (m/f/d)", "Acme", "Backend Engineer | Remote"),
            ("Example Labs Pvt Ltd", "AI Engineer (Remote)", "example labs", "AI Engineer"),
            ("Acme", "Data Analyst (Fresher, Bengaluru)", "Acme", "Data Analyst")]
    for c1, t1, c2, t2 in same:
        assert fingerprint(c1, t1) == fingerprint(c2, t2), (t1, t2)


def test_different_roles_stay_apart():
    apart = [("Cisco", "Software Engineer - Go, Java Dockers, Kubernetes, AWS", "Cisco", "Software Engineer - C/C++ Networking & Security"),
             ("Mastercard", "Software Engineer II", "Mastercard", "Software Engineer II | Data & AI Platform"),
             ("Amazon", "SDE I FTC", "Amazon", "SDE I"),
             ("Acme", "AI Engineer", "Other Co", "AI Engineer"),
             ("Acme", "Software Engineer II", "Acme", "Software Engineer III"),
             ("Cisco", "Solutions Engineer (Customer Experience)", "Cisco", "Solutions Engineer (Security, GSSO) - Mumbai")]
    for c1, t1, c2, t2 in apart:
        assert fingerprint(c1, t1) != fingerprint(c2, t2), (t1, t2)
    assert title_key("Software Engineer - C/C++ programmer, Linux - 5 to 8 years - Bangalore").endswith("5 to 8 years")


def test_agent_filter_keeps_one_of_each_role(tmp_path):
    base = {"facts": {"loc": "remote-worldwide", "expMin": 0}, "summary": "Python.", "via": "careers", "location": "Remote",
            "postedAt": "", "workMode": "remote", "source": "Greenhouse"}
    recs = [dict(base, id="a", company="Tether", title="Mobile Engineer - React Native (100% Remote)", url="https://t.example/1"),
            dict(base, id="b", company="Tether Operations Limited", title="Mobile Engineer - React Native (100% Remote) - Worldwide", url="https://agg.example/2"),
            dict(base, id="c", company="Amazon", title="SDE I FTC", url="https://amazon.example/3"),
            dict(base, id="d", company="Amazon", title="Software Development Engineer I FTC", url="https://amazon.example/4"),
            dict(base, id="e", company="Amazon", title="Software Development Engineer I", url="https://amazon.example/5")]
    feed = tmp_path / "f.jsonl.gz"
    with gzip.open(feed, "wt", encoding="utf-8") as f:
        f.write("\n".join(json.dumps(r) for r in recs))
    known = tmp_path / "known" / "jobs"
    known.mkdir(parents=True)
    (known / "old.json").write_text(json.dumps({"company": "Amazon", "title": "SDE-1", "url": "https://amazon.example/old"}))
    sett = tmp_path / "s.json"
    sett.write_text(json.dumps({"maxRequiredYears": 1, "targetRoles": ["Engineer", "SDE"], "locations": ["Remote worldwide (first priority)"]}))
    out = tmp_path / "out"
    subprocess.run([sys.executable, str(SCRIPT), str(feed), str(sett), str(tmp_path / "known"), str(out), "50"], check=True, capture_output=True)
    kept = json.loads((out / "index.json").read_text())["kept"]
    assert sorted(kept) == ["a", "c"]  # b repeats a, d repeats c, e repeats the SDE-1 already on the dashboard
