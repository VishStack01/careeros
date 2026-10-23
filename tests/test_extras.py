"""Pay comparison, funded-company discovery and the doctor."""

import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from careeros import doctor, funded, salary_gap

ROOT = Path(__file__).resolve().parents[1]


def test_salary_gap():
    r = salary_gap.compare("₹18-24 LPA", 22, 10, "₹19 LPA", [{"round": "Recruiter", "amount": 22}, {"round": "Hiring manager", "amount": "20 LPA"}])
    assert [x["what"] for x in r["rows"]] == ["Posting advertised", "Your floor", "Your ask", "Offer"]
    assert any("17% of the way up" in f for f in r["findings"]) and any("3 LPA under your ask" in f for f in r["findings"])
    assert not r["consistent"] and any("different numbers" in f for f in r["findings"])
    assert any("lower bound" in f for f in salary_gap.compare("18-24 LPA", offer="15 LPA")["findings"])
    assert any("under your floor" in f for f in salary_gap.compare(floor=10, offer="8 LPA")["findings"])
    usd = salary_gap.compare("$30–40K a year", offer="$32K")
    assert usd["rows"][0]["lpa"] == "26.4–35.2 LPA" and any("₹88" in f for f in usd["findings"])
    job = {"salary": "9–12 LPA", "offer": {"ctc": "11 LPA"}, "evaluation": {"comp": {"advertised": "9–12 LPA"}}}
    assert salary_gap.for_job(job, {"salaryFloorLpa": 10}, {"expectedCtcLpa": 12})["rows"][-1]["lpa"] == "11 LPA"


RSS = b"""<?xml version="1.0"?><rss version="2.0"><channel>
<item><title>Bengaluru-Based Fintech Startup Quillo Raises $6 Mn In Series A Led By Omidyar</title><link>https://inc42.example/quillo</link><pubDate>Mon, 19 Oct 2026 08:00:00 +0530</pubDate></item>
<item><title>Exclusive: Stealth SaaS Startup Zipto Bags INR 40 Cr In Seed Round</title><link>https://entrackr.example/zipto</link><pubDate>Sun, 18 Oct 2026 08:00:00 +0530</pubDate></item>
<item><title>Funding Roundup: Indian Startups Raised $200 Mn This Week</title><link>https://inc42.example/roundup</link><pubDate>Sat, 17 Oct 2026 08:00:00 +0530</pubDate></item>
<item><title>AI startup Sarvam AI raises $41 million in Series A funding</title><link>https://tc.example/sarvam</link><pubDate>Fri, 16 Oct 2026 08:00:00 +0530</pubDate></item>
<item><title>Old News Co raises $1 Mn</title><link>https://x.example/old</link><pubDate>Mon, 01 Jun 2026 08:00:00 +0530</pubDate></item>
<item><title>How this founder built a unicorn</title><link>https://x.example/story</link><pubDate>Mon, 19 Oct 2026 08:00:00 +0530</pubDate></item>
</channel></rss>"""


def test_funding_headline_prefixes():
    assert funded.headline("[Update] TravClan Raises $5 Mn In Series A")["company"] == "TravClan"
    assert funded.headline("Y Combinator-Backed Firstwork Raises $15 Mn")["company"] == "Firstwork"
    assert funded.headline("Peak XV-Backed Acme Bags INR 40 Cr")["company"] == "Acme"


def test_funded(tmp_path):
    items = funded.parse_feed(RSS)
    assert len(items) == 6 and items[0]["link"] == "https://inc42.example/quillo"
    found = funded.candidates(items, funded.known_keys(ROOT / "config" / "companies" / "companies.csv"), days=30,
                              now=datetime(2026, 10, 21, tzinfo=timezone.utc))
    by = {c["company"]: c for c in found}
    assert set(by) == {"Quillo", "Zipto", "Sarvam AI"}
    assert by["Quillo"]["amount"] == "$6 Mn" and by["Quillo"]["round"] == "Series A" and not by["Quillo"]["tracked"]
    assert by["Sarvam AI"]["tracked"]  # already in the company list
    csv_path = tmp_path / "companies.csv"
    csv_path.write_text("name,category,city,website,slugs,ats,token,source\nSarvam AI,ai-native,Bengaluru,,,,,curated\n", encoding="utf-8")
    assert funded.add(["Quillo", "Sarvam AI"], found, csv_path) == ["Quillo"]
    assert "Quillo,funded" in csv_path.read_text(encoding="utf-8")
    assert funded.add(["Quillo"], found, csv_path) == []  # once only


def test_doctor(tmp_path):
    res = doctor.checks(tmp_path, str(tmp_path / "x.db"))
    what = " | ".join(w for _, w, _ in res)
    assert "Python" in what and "No Career Brain yet" in what and "Database" in what
    assert not any(lvl == "FAIL" for lvl, _, _ in res)
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    (tmp_path / "brain").mkdir()
    (tmp_path / "brain" / "brain.json").write_text("{}", encoding="utf-8")
    subprocess.run(["git", "-C", str(tmp_path), "add", "brain/brain.json"], check=True)
    res = doctor.checks(tmp_path, str(tmp_path / "x.db"))
    assert any(lvl == "FAIL" and "brain/brain.json" in w for lvl, w, _ in res)
    r = subprocess.run([sys.executable, "-m", "careeros", "--db", str(tmp_path / "y.db"), "doctor"], capture_output=True, text=True, cwd=tmp_path)
    assert r.returncode == 1 and "Private files tracked by git" in r.stdout
