"""Find each company's public job board.

For every company in config/companies/companies.csv we try its likely board
slugs on each hiring system's public feed, in order of how common they are
among Indian product companies. The first board that checks out is recorded.

"Checks out" means: the feed exists, the board's own company name matches
ours when the feed reports one, and for India-headquartered companies at least
one opening is in India or remote (a board full of US-only roles under the same
slug is usually a different company with the same name).

Results are cached in feed/boards.json. Unmapped companies are re-tried after
`refresh_days`; they use career sites the scan can't read (Darwinbox, Keka,
Zoho Recruit, custom pages) and are visited by the agent instead.
"""

from __future__ import annotations

import csv
import json
import re
import time
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
from pathlib import Path

from . import geo
from .models import iso
from .sources import http

ATS_ORDER = ["greenhouse", "lever", "ashby", "smartrecruiters", "recruitee", "breezy", "personio", "workable"]
# Workable rate-limits hard and answers for any name with an empty board, so it
# is tried last and with the first slug only, unless the company list names it.
SLUGS_PER_ATS = {"workable": 1}
GLOBAL_CATEGORIES = {"global-india-engineering", "remote-first-global", "yc-remote"}
PROBE_INTERVAL = 0.25  # seconds between requests to one host while discovering
_deadline = [float("inf")]  # time.monotonic() after which no new company is started


def _norm(s: str) -> str:
    s = re.sub(r"\b(ai|labs?|technologies|technology|inc|pvt|ltd|private|limited|india|hq|app|the|careers|jobs)\b", " ", (s or "").lower())
    return re.sub(r"[^a-z0-9]", "", s)


def names_match(a: str, b: str) -> bool:
    na, nb = _norm(a), _norm(b)
    if not na or not nb:
        return False
    return na == nb or (len(min(na, nb, key=len)) >= 4 and (na in nb or nb in na))


def _get(url):
    return http.get_json(url, timeout=10, retries=1, min_interval=PROBE_INTERVAL)


def probe(ats: str, slug: str) -> dict | None:
    """Return {"board_name", "locations": [..]} if `slug` is a live board on `ats`, else None."""
    try:
        if ats == "greenhouse":
            jobs = _get(f"https://boards-api.greenhouse.io/v1/boards/{slug}/jobs").get("jobs", [])
            try:
                name = _get(f"https://boards-api.greenhouse.io/v1/boards/{slug}").get("name", "")
            except http.FetchError:
                name = ""
            return {"board_name": name, "locations": [(j.get("location") or {}).get("name", "") for j in jobs]}
        if ats == "lever":
            data = _get(f"https://api.lever.co/v0/postings/{slug}?mode=json")
            if not isinstance(data, list):
                return None
            return {"board_name": "", "locations": [((j.get("categories") or {}).get("location") or "") + (" remote" if j.get("workplaceType") == "remote" else "") for j in data]}
        if ats == "ashby":
            data = _get(f"https://api.ashbyhq.com/posting-api/job-board/{slug}")
            if "jobs" not in data:
                return None
            return {"board_name": "", "locations": [(j.get("location") or "") + (" remote" if j.get("isRemote") else "") for j in data["jobs"]]}
        if ats == "workable":
            data = _get(f"https://apply.workable.com/api/v1/widget/accounts/{slug}")
            if "jobs" not in data:
                return None
            locs = [", ".join(x for x in (j.get("city"), j.get("country")) if x) + (" remote" if j.get("telecommuting") else "") for j in data["jobs"]]
            return {"board_name": data.get("name", ""), "locations": locs}
        if ats == "smartrecruiters":
            data = _get(f"https://api.smartrecruiters.com/v1/companies/{slug}/postings?limit=100")
            content = data.get("content", [])
            if not content:
                return None  # unknown ids also answer 200 with nothing in them
            name = (content[0].get("company") or {}).get("name", "")
            locs = [((j.get("location") or {}).get("fullLocation") or (j.get("location") or {}).get("country", "")) + (" remote" if (j.get("location") or {}).get("remote") else "") for j in content]
            return {"board_name": name, "locations": locs}
        if ats == "recruitee":
            data = _get(f"https://{slug}.recruitee.com/api/offers/")
            if "offers" not in data:
                return None
            return {"board_name": "", "locations": [(o.get("location") or o.get("country") or "") + (" remote" if o.get("remote") else "") for o in data["offers"]]}
        if ats == "breezy":
            data = _get(f"https://{slug}.breezy.hr/json")
            if not isinstance(data, list):
                return None
            return {"board_name": "", "locations": [((j.get("location") or {}).get("name") or "") + (" remote" if (j.get("location") or {}).get("is_remote") else "") for j in data]}
        if ats == "personio":
            text = http.get_text(f"https://{slug}.jobs.personio.de/xml", timeout=10, retries=1, min_interval=PROBE_INTERVAL)
            if "<workzag-jobs" not in text:
                return None
            root = ET.fromstring(text)
            return {"board_name": "", "locations": [(p.findtext("office") or "") for p in root.findall("position")]}
    except (http.FetchError, ET.ParseError, ValueError, AttributeError):
        return None
    return None


def _india_or_remote(loc: str) -> bool:
    return geo.classify(loc)["india"] or bool(re.search(r"remote|anywhere|worldwide|apac", loc or "", re.I))


def accept(company: dict, found: dict) -> tuple[bool, str]:
    """Is this board really this company's? Returns (ok, confidence).

    A board with no openings is never accepted: some systems (Workable,
    Breezy) answer for any name with an empty board, so an empty board proves
    nothing. Those companies are re-checked after a few days instead."""
    if not found.get("locations"):
        return False, "empty"
    if found.get("board_name"):
        if not names_match(company["name"], found["board_name"]):
            return False, "name-mismatch"
        conf = "name"
    else:
        conf = "slug"
    locs = found.get("locations", [])
    if company.get("category") in GLOBAL_CATEGORIES:
        return True, conf
    if any(_india_or_remote(l) for l in locs):
        return True, conf + "+india"
    return (True, conf) if conf == "name" else (False, "no-india-roles")


def discover_one(company: dict) -> dict | None:
    if time.monotonic() > _deadline[0]:
        return None  # out of time this run; it stays due for the next one
    now = iso(datetime.now(timezone.utc))
    tried = 0
    pairs: list[tuple[str, str]] = []
    if company.get("ats") and company.get("token"):
        pairs.append((company["ats"], company["token"]))
    slugs = [s for s in company.get("slugs", []) if s][:4]
    for ats in ATS_ORDER:
        for slug in slugs[: SLUGS_PER_ATS.get(ats, len(slugs))]:
            pairs.append((ats, slug))
    empty = False
    for ats, slug in pairs:
        if time.monotonic() > _deadline[0] + 180:
            return None  # well past the time budget: leave the rest of this company for the next run
        tried += 1
        found = probe(ats, slug)
        if not found:
            continue
        ok, conf = accept(company, found)
        if ok:
            return {"status": "mapped", "ats": ats, "token": slug, "confidence": conf,
                    "boardName": found.get("board_name", ""), "openings": len(found.get("locations", [])), "checkedAt": now}
        empty = empty or conf == "empty"
    out = {"status": "unmapped", "checkedAt": now, "probes": tried}
    if empty:
        out["retryDays"] = 3  # an empty board may be real and start hiring soon
    return out


def load_companies(path: str | Path) -> list[dict]:
    rows = []
    with open(path, newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            r["slugs"] = (r.get("slugs") or "").split()
            rows.append(r)
    return rows


def run(companies_csv: str | Path, cache_path: str | Path, refresh_days: int = 14, workers: int = 32,
        limit: int | None = None, max_minutes: float | None = None, log=print) -> dict:
    companies = load_companies(companies_csv)
    cache_path = Path(cache_path)
    cache = json.loads(cache_path.read_text()) if cache_path.exists() else {"companies": {}}
    known = cache.setdefault("companies", {})
    now = datetime.now(timezone.utc)

    def due(c):
        e = known.get(c["name"])
        if not e:
            return True
        if e.get("status") == "mapped":
            # Re-check boards that errored, and boards accepted while empty by older versions.
            return bool(e.get("stale")) or str(e.get("confidence", "")).endswith("-empty")
        try:
            last = datetime.fromisoformat(e.get("checkedAt", "").replace("Z", "+00:00"))
        except ValueError:
            return True
        return now - last > timedelta(days=e.get("retryDays", refresh_days))

    todo = [c for c in companies if due(c)]
    if limit:
        todo = todo[:limit]
    log(f"Discovering boards for {len(todo)} of {len(companies)} companies…")
    _deadline[0] = time.monotonic() + max_minutes * 60 if max_minutes else float("inf")
    skipped = 0
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futs = {pool.submit(discover_one, c): c for c in todo}
        for i, fut in enumerate(as_completed(futs), 1):
            c = futs[fut]
            try:
                res = fut.result()
            except Exception as e:  # one bad company never stops the run
                res = {"status": "error", "error": str(e)[:200], "checkedAt": iso(now)}
            if res is None:
                skipped += 1
                continue
            known[c["name"]] = {"category": c.get("category", ""), "city": c.get("city", ""), "website": c.get("website", ""), **res}
            if i % 50 == 0:
                log(f"  {i}/{len(todo)} checked")
    for c in companies:  # keep metadata current for every company
        e = known.setdefault(c["name"], {"status": "pending"})
        e["category"], e["city"] = c.get("category", ""), c.get("city", "")
    cache["generatedAt"] = iso(datetime.now(timezone.utc))
    mapped = sum(1 for e in known.values() if e.get("status") == "mapped")
    cache["stats"] = {"companies": len(companies), "mapped": mapped,
                      "byAts": {a: sum(1 for e in known.values() if e.get("ats") == a and e.get("status") == "mapped") for a in ATS_ORDER}}
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(json.dumps(cache, indent=1, ensure_ascii=False), encoding="utf-8")
    if skipped:
        log(f"  time budget reached; {skipped} companies left for the next run")
    log(f"Mapped {mapped} of {len(companies)} companies to a public job board.")
    return cache
