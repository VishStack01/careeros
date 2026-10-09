"""Scan every mapped company board and publish the India feed.

Sources: every mapped company board (feed/boards.json) plus the remote job
boards with public feeds (sources/aggregators.py).

Output (in `out_dir`):
  india.jsonl.gz   one line per open tech role in India or remote, with
                   pre-extracted facts (experience, remote scope, pay, closed)
  summary.json     counts by hiring system and region, errors
  unmapped.csv     companies whose career site isn't on a public feed; the
                   agent visits these in rotation

The feed is deliberately not filtered by anyone's personal settings: it is a
public list of openings. `careeros filter-feed` applies your filters.
"""

from __future__ import annotations

import csv
import gzip
import hashlib
import json
import re
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

from . import extract, geo
from .dedupe import canonical_url, fingerprint, job_id
from .models import Job, iso
from .sources import SCOUTS, FetchError, smartrecruiters
from .sources.aggregators import AGGREGATORS, MIN_HOURS

TECH = re.compile(
    r"engineer|developer|scientist|machine learning|\bml\b|\bai\b|genai|\bllm|data|analyst|research|designer|"
    r"product manager|automation|\bsde\b|\bswe\b|devops|\bsre\b|platform|backend|back end|front ?end|full[ -]?stack|"
    r"mobile|android|\bios\b|\bqa\b|\btest|security|intern|graduate|trainee|architect|prompt|nlp|vision|robotics|"
    r"forward deployed|solutions? engineer|applied",
    re.I,
)


def _ts(s: str | None) -> float:
    try:
        return datetime.fromisoformat((s or "").replace("Z", "+00:00")).timestamp()
    except ValueError:
        return 0.0


def relevant_location(job: Job) -> bool:
    where = geo.classify(job.location)
    return where["india"] or job.work_mode == "remote" or bool(re.search(r"remote|anywhere|worldwide|apac|asia", job.location or "", re.I))


def to_feed(job: Job, company: dict, via: str = "careers") -> dict:
    url = canonical_url(job.url)
    f = extract.facts(job.description, str(job.raw.get("experience_header", "")), job.location, job.salary_text)
    summary = re.sub(r"\s+", " ", job.description or "").strip()[:1500]
    where = geo.classify(job.location)
    return {
        "id": job_id(job.company, job.title)[:70] + "-" + hashlib.sha1(url.encode()).hexdigest()[:6],
        "company": job.company, "title": job.title, "url": url, "source": job.source,
        "location": job.location, "workMode": job.work_mode, "postedAt": job.posted_at,
        "salary": job.salary_text, "experienceHeader": str(job.raw.get("experience_header", "")),
        "category": company.get("category", ""), "hq": company.get("city", ""),
        "geo": "south" if where["south"] else "india" if where["india"] else "abroad" if where["abroad"] else "",
        "facts": f, "summary": summary, "via": via,
    }


def scan_board(name: str, entry: dict, detail_budget: list[int]) -> tuple[list[dict], str | None]:
    scout = SCOUTS.get(entry.get("ats", ""))
    if not scout:
        return [], f"{name}: unknown ATS {entry.get('ats')}"
    try:
        jobs = scout(entry["token"], name)
    except FetchError as e:
        return [], f"{name} ({entry['ats']}:{entry['token']}): {e}"
    out = []
    for j in jobs:
        j.company = name
        if not TECH.search(j.title or "") or not relevant_location(j):
            continue
        if j.raw.get("needs_detail") and detail_budget[0] > 0:
            detail_budget[0] -= 1
            try:
                smartrecruiters.describe(j)
            except FetchError:
                pass
        out.append(to_feed(j, entry))
    return out, None


def scan_aggregator(name: str, cache_dir: Path, now: datetime) -> tuple[list[dict], str | None, bool]:
    """(records, error, fresh). Reuses the last result until the board's polling interval has passed."""
    cache = cache_dir / f"{name}.json.gz"
    prev = None
    if cache.exists():
        try:
            with gzip.open(cache, "rt", encoding="utf-8") as f:
                prev = json.load(f)
        except (OSError, ValueError):
            prev = None
    if prev:
        age_h = (now - datetime.fromisoformat(prev["fetchedAt"].replace("Z", "+00:00"))).total_seconds() / 3600
        if age_h < MIN_HOURS.get(name, 3) - 0.25:
            return prev["records"], None, False
    try:
        jobs = AGGREGATORS[name]()
    except (FetchError, ValueError, KeyError, TypeError, AttributeError, ET.ParseError) as e:
        return (prev or {}).get("records", []), f"{name}: {e}"[:300], False
    recs = [to_feed(j, {"category": "remote-board"}, via="board") for j in jobs
            if j.title and j.url and TECH.search(j.title) and relevant_location(j)]
    cache_dir.mkdir(parents=True, exist_ok=True)
    with gzip.open(cache, "wt", encoding="utf-8") as f:
        json.dump({"fetchedAt": iso(now), "records": recs}, f, ensure_ascii=False)
    return recs, None, True


def run(boards_path: str | Path, out_dir: str | Path, workers: int = 16, detail_cap: int = 400,
        aggregators: bool = True, log=print) -> dict:
    boards = json.loads(Path(boards_path).read_text())
    companies = boards.get("companies", {})
    mapped = {n: e for n, e in companies.items() if e.get("status") == "mapped"}
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    records: list[dict] = []
    errors: list[str] = []
    budget = [detail_cap]
    log(f"Scanning {len(mapped)} company boards…")
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futs = {pool.submit(scan_board, n, e, budget): n for n, e in mapped.items()}
        for fut in as_completed(futs):
            recs, err = fut.result()
            records += recs
            if err:
                errors.append(err)
                companies[futs[fut]]["stale"] = True  # re-discover next time
            else:
                companies[futs[fut]].pop("stale", None)
    board_counts: dict[str, int] = {}
    if aggregators and AGGREGATORS:
        now = datetime.now(timezone.utc)
        with ThreadPoolExecutor(max_workers=len(AGGREGATORS)) as pool:
            futs = {pool.submit(scan_aggregator, n, out_dir / "boards-cache", now): n for n in AGGREGATORS}
            for fut in as_completed(futs):
                recs, err, _fresh = fut.result()
                board_counts[futs[fut]] = len(recs)
                records += recs
                if err:
                    errors.append(err)
    # Company pages first: when a remote board re-lists a company's role, keep the company's own posting.
    seen, fps, unique = set(), set(), []
    for r in sorted(records, key=lambda r: (r.get("via") == "board", -_ts(r.get("postedAt")))):
        fp = fingerprint(r["company"], r["title"])
        if r["url"] in seen or (r.get("via") == "board" and fp in fps):
            continue
        seen.add(r["url"])
        fps.add(fp)
        unique.append(r)
    unique.sort(key=lambda r: -_ts(r.get("postedAt")))
    with gzip.open(out_dir / "india.jsonl.gz", "wt", encoding="utf-8") as f:
        for r in unique:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    with (out_dir / "unmapped.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["name", "category", "city", "website"])
        for n, e in sorted(companies.items()):
            if e.get("status") != "mapped":
                w.writerow([n, e.get("category", ""), e.get("city", ""), e.get("website", "")])
    summary = {
        "generatedAt": iso(datetime.now(timezone.utc)),
        "companies": len(companies), "boards": len(mapped), "openings": len(unique),
        "remoteBoards": board_counts, "byAts": {}, "byGeo": {}, "errors": len(errors), "errorSamples": errors[:20],
        "erroredCompanies": sorted(n for n, e in companies.items() if e.get("stale")),
    }
    for r in unique:
        summary["byAts"][r["source"]] = summary["byAts"].get(r["source"], 0) + 1
        summary["byGeo"][r["geo"] or "remote/unknown"] = summary["byGeo"].get(r["geo"] or "remote/unknown", 0) + 1
    (out_dir / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    Path(boards_path).write_text(json.dumps(boards, indent=1, ensure_ascii=False), encoding="utf-8")
    log(f"Feed: {len(unique)} open tech roles in India or remote from {len(mapped)} company boards "
        f"and {len(board_counts)} remote job boards ({len(errors)} errors).")
    return summary
