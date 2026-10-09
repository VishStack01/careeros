"""Apply your personal filters to the public India feed.

  careeros filter-feed --feed <url-or-path> --settings-json settings.json \
      --known known/ --out new/

Writes one JSON document per kept role to new/kept/, near-misses (in your field,
failing exactly one gate) to new/skipped/, and new/index.json with counts. Each
file is a dashboard job document, ready to store.
"""

from __future__ import annotations

import gzip
import io
import json
import re
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

from .dedupe import canonical_url, fingerprint
from .gates import apply_decision
from .models import Job
from .settings import LocationPolicy, Settings

NEAR_MISS_GATES = {"Experience", "Posted", "Location", "Pay", "Seniority"}


def load_feed(src: str) -> list[dict]:
    if re.match(r"https?://", src):
        raw = urllib.request.urlopen(urllib.request.Request(src, headers={"User-Agent": "careeros"}), timeout=60).read()
    else:
        raw = Path(src).read_bytes()
    if raw[:2] == b"\x1f\x8b":
        raw = gzip.decompress(raw)
    return [json.loads(line) for line in io.StringIO(raw.decode("utf-8")) if line.strip()]


def settings_from_dashboard(doc: dict) -> Settings:
    """Turn the dashboard's settings/profile document into gate settings."""
    s = Settings()
    if doc.get("maxRequiredYears") is not None:
        s.max_required_years = float(doc["maxRequiredYears"])
    if doc.get("maxPostingAgeDays"):
        s.max_posting_age_days = int(doc["maxPostingAgeDays"])
    floor = doc.get("salaryFloorLpa")
    s.salary_floor_lpa = float(floor) if floor not in (None, "", 0) else None
    if doc.get("targetRoles"):
        s.role_keywords = [r.lower() for r in doc["targetRoles"]] + s.role_keywords
    if doc.get("dealbreakers"):
        s.dealbreakers = [d.strip() for d in re.split(r"[,\n]", str(doc["dealbreakers"])) if d.strip()]
    if doc.get("companyBlocklist"):
        s.company_blocklist = list(doc["companyBlocklist"])
    locs = " ".join(doc.get("locations") or []).lower()
    if locs:
        s.location = LocationPolicy(
            south_india="any" if "south india (any" in locs or "bengaluru" in locs or "hyderabad" in locs else ("remote" if "south india (remote" in locs else "never"),
            rest_of_india="remote" if "rest of india (remote" in locs or "remote (india)" in locs else ("any" if "rest of india (any" in locs else "never"),
            abroad="remote" if "worldwide" in locs or "global" in locs else "never",
        )
    return s


def load_known(path: str | None) -> tuple[set[str], set[str], set[str]]:
    """(ids, canonical urls, company+title fingerprints) of roles already on the dashboard."""
    ids, urls, fps = set(), set(), set()
    if not path:
        return ids, urls, fps
    p = Path(path)
    files = list(p.rglob("*.json")) if p.is_dir() else [p]
    for f in files:
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            continue
        items = data if isinstance(data, list) else [data]
        for it in items:
            doc = it.get("data", it) if isinstance(it, dict) else {}
            ids.add(it.get("id") or f.stem)
            if doc.get("url"):
                urls.add(canonical_url(doc["url"]))
            if doc.get("company") and doc.get("title"):
                fps.add(fingerprint(doc["company"], doc["title"]))
    return ids, urls, fps


def _known_docs(path: str | None) -> list[tuple[str, dict]]:
    if not path:
        return []
    p = Path(path)
    out = []
    for f in (list(p.rglob("*.json")) if p.is_dir() else [p]):
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            continue
        for it in (data if isinstance(data, list) else [data]):
            if isinstance(it, dict):
                out.append((it.get("id") or f.stem, it.get("data", it)))
    return out


def load_summary(feed_src: str) -> dict | None:
    """summary.json next to the feed (same folder or URL), or None."""
    src = re.sub(r"india\.jsonl\.gz$", "summary.json", feed_src)
    if src == feed_src:
        return None
    try:
        if re.match(r"https?://", src):
            raw = urllib.request.urlopen(urllib.request.Request(src, headers={"User-Agent": "careeros"}), timeout=30).read()
        else:
            raw = Path(src).read_bytes()
        return json.loads(raw)
    except (OSError, ValueError):
        return None


def stale(known: list[tuple[str, dict]], feed_urls: set[str], summary: dict | None, settings: Settings, now: datetime) -> dict:
    """Roles on the dashboard the feed shows are gone or past your window.

    gone: found via the feed, still at stage "found", and no longer listed on a
          board that was read successfully this scan (so it closed).
    expired: still at stage "found" and posted before your window."""
    gone, expired = [], []
    errored = set((summary or {}).get("erroredCompanies", []))
    for doc_id, d in known:
        if d.get("stage") not in ("found", None, ""):
            continue
        posted = d.get("postedAt") or ""
        try:
            dt = datetime.fromisoformat(posted.replace("Z", "+00:00"))
            dt = dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
            if (now - dt).days > settings.max_posting_age_days:
                expired.append(doc_id)
                continue
        except ValueError:
            pass
        if (summary and d.get("foundVia") in ("careers-feed", "remote-board") and d.get("url")
                and canonical_url(d["url"]) not in feed_urls and d.get("company") not in errored):
            gone.append(doc_id)
    return {"gone": gone, "expired": expired}


def _about(summary: str) -> str:
    s = re.sub(r"\s+", " ", summary or "").strip()
    m = re.match(r"(.{40,260}?[.!?])\s", s + " ")
    return m.group(1) if m else s[:240]


def run(feed_src: str, settings: Settings, known_path: str | None, out_dir: str | Path,
        max_skips: int = 60, max_kept: int = 400, now: datetime | None = None, summary: dict | None = None) -> dict:
    now = now or datetime.now(timezone.utc)
    records = load_feed(feed_src)
    summary = summary if summary is not None else load_summary(feed_src)
    ids, urls, fps = load_known(known_path)
    out = Path(out_dir)
    (out / "kept").mkdir(parents=True, exist_ok=True)
    (out / "skipped").mkdir(parents=True, exist_ok=True)
    kept, skipped, known = [], [], 0
    for r in records:
        if r["id"] in ids or canonical_url(r["url"]) in urls or fingerprint(r["company"], r["title"]) in fps:
            known += 1
            continue
        board = r.get("via") == "board"
        job = Job(company=r["company"], title=r["title"], url=r["url"],
                  source=r["source"] if board else f"{r['source']} (company careers page)",
                  location=r.get("location", ""), work_mode=r.get("workMode", ""), description=r.get("summary", ""),
                  posted_at=r.get("postedAt", ""), salary_text=r.get("salary", ""),
                  raw={"facts": r.get("facts") or {}, "experience_header": r.get("experienceHeader", "")})
        d = apply_decision(job, settings, now)
        failed = [c.gate for c in d.checks if not c.passed]
        role_ok = "Role" not in failed and "Company" not in failed
        if not d.kept and not (role_ok and len(failed) == 1 and failed[0] in NEAR_MISS_GATES):
            continue
        doc = job.to_record()
        doc["brief"] = {"about": _about(r.get("summary", "")),
                        "sources": [{"title": f"{r['source']} listing" if board else f"{r['company']} careers page", "url": r["url"]}]}
        doc["foundVia"] = "remote-board" if board else "careers-feed"
        if r.get("facts", {}).get("applicants"):
            doc["applicants"] = r["facts"]["applicants"]
        if d.kept:
            kept.append((r["id"], doc))
        else:
            doc["skip"]["wouldChange"] = {
                "Experience": "Raising your experience limit.", "Posted": "A wider posting window.",
                "Location": "Allowing this location or work mode.", "Pay": "A lower pay floor.", "Seniority": "Allowing senior titles.",
            }.get(failed[0], "")
            skipped.append((r["id"], doc))
    order = {"remote-global": 0, "remote-india": 1, "south-india": 2}
    kept.sort(key=lambda x: (order.get(x[1].get("region", ""), 9), -(datetime.fromisoformat(x[1]["postedAt"].replace("Z", "+00:00")).timestamp() if x[1].get("postedAt") else 0)))
    kept, skipped = kept[:max_kept], skipped[:max_skips]
    for sub, items in (("kept", kept), ("skipped", skipped)):
        for doc_id, doc in items:
            (out / sub / f"{doc_id}.json").write_text(json.dumps(doc, ensure_ascii=False), encoding="utf-8")
    index = {"feedRecords": len(records), "alreadyKnown": known, "kept": [i for i, _ in kept], "skipped": [i for i, _ in skipped],
             "byRegion": {k: sum(1 for _, d in kept if d.get("region") == k) for k in order}}
    index.update(stale(_known_docs(known_path), {canonical_url(r["url"]) for r in records}, summary, settings, now))
    if summary:
        index["feed"] = {k: summary.get(k) for k in ("generatedAt", "companies", "boards", "openings", "remoteBoards")}
    (out / "index.json").write_text(json.dumps(index, indent=2), encoding="utf-8")
    return index
