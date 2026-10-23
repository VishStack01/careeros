"""Hiring radar: learn which companies are hiring from the big job boards, then
read those companies' own job boards.

    careeros radar --config config/radar.toml --boards feed/boards.json --out feed/radar-companies.csv

JobSpy (MIT, github.com/speedyapply/JobSpy) searches Indeed India and Naukri
(LinkedIn and Glassdoor too, if you turn them on). CareerOS keeps none of those
listings. From each result it takes only two things:

* the employer's own application link, when the board gives one: if it is a
  Greenhouse, Lever, Ashby, SmartRecruiters, Workable, Recruitee, Breezy or
  Personio page, that company's whole board is added to the scan at once;
* otherwise the company's name, which goes to `careeros discover` to find its
  job board the usual way.

So every role on the board and the dashboard is still the employer's own
posting, with its full text and the quotes the checks rely on, and applications
still go to the company's site, never to Indeed, Naukri or LinkedIn.

Needs: pip install "careeros[radar]" (it installs python-jobspy).
"""

from __future__ import annotations

import csv
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable
from urllib.parse import parse_qs, urlparse

try:  # Python 3.11+
    import tomllib
except ModuleNotFoundError:  # pragma: no cover
    tomllib = None

DEFAULTS = {
    "sites": ["indeed", "naukri"],
    "terms": ["software engineer", "AI engineer", "machine learning engineer", "product designer",
              "frontend developer", "backend developer", "full stack developer", "data analyst"],
    "locations": ["Bengaluru", "Hyderabad", "Chennai"],
    "remote": True,
    "hours_old": 72,
    "results_per_query": 40,
    "max_minutes": 8,
}

# Staffing and consulting firms post for clients; their own board isn't where the role lives.
_AGENCY = re.compile(r"\b(consult\w*|staffing|recruit\w*|placement\w*|manpower|hr solutions|talent (acquisition|solutions)|outsourcing|"
                     r"confidential|hiring for|client of)\b", re.I)


def board_from_url(url: str) -> tuple[str, str] | None:
    """(ats, token) when `url` is a posting or board on a hiring system the scan reads."""
    if not url:
        return None
    u = urlparse(url.strip())
    host, parts = u.netloc.lower().split(":")[0], [p for p in u.path.split("/") if p]
    q = parse_qs(u.query)
    if host.endswith("greenhouse.io"):
        if "for" in q:
            return "greenhouse", q["for"][0].lower()
        if host.split(".")[0] in ("boards", "job-boards") and parts and parts[0] not in ("embed", "v1"):
            return "greenhouse", parts[0].lower()
        return None
    if host in ("jobs.lever.co", "jobs.eu.lever.co") and parts:
        return "lever", parts[0].lower()
    if host == "jobs.ashbyhq.com" and parts:
        return "ashby", parts[0]
    if host in ("jobs.smartrecruiters.com", "careers.smartrecruiters.com") and parts:
        return "smartrecruiters", parts[0]
    if host == "apply.workable.com" and parts and parts[0] not in ("j", "api"):
        return "workable", parts[0].lower()
    if host.endswith(".myworkdayjobs.com"):
        from .workday import token_from_url
        tok = token_from_url(url.strip())
        return ("workday", tok) if tok else None
    m = re.match(r"^([a-z0-9-]+)\.(recruitee\.com|breezy\.hr|jobs\.personio\.(?:de|com))$", host)
    if m and m.group(1) not in ("www", "app", "api"):
        kind = {"recruitee.com": "recruitee", "breezy.hr": "breezy"}.get(m.group(2), "personio")
        return kind, m.group(1)
    return None


def slugs_for(name: str) -> list[str]:
    """Likely board names for a company, the way the curated list writes them."""
    base = re.sub(r"\b(private|pvt|limited|ltd|llp|inc|technologies|technology|solutions|software|systems|india|the)\b\.?", " ", name.lower())
    words = re.findall(r"[a-z0-9]+", base)
    if not words:
        return []
    out = ["".join(words), "-".join(words), words[0]]
    return [s for s in dict.fromkeys(out) if len(s) >= 3][:3]


def load_config(path: str | Path | None) -> dict:
    cfg = dict(DEFAULTS)
    if path and Path(path).exists() and tomllib:
        cfg.update(tomllib.loads(Path(path).read_text(encoding="utf-8")))
    return cfg


def search(cfg: dict, scrape: Callable | None = None, log=print) -> list[dict]:
    """Run the configured searches. Each result is a plain dict of JobSpy's columns."""
    if scrape is None:
        try:
            from jobspy import scrape_jobs as scrape  # type: ignore
        except ImportError:
            log('Hiring radar is off: pip install "careeros[radar]" to turn it on.')
            return []
    deadline = time.monotonic() + float(cfg.get("max_minutes", 8)) * 60
    rows: list[dict] = []
    sites = list(cfg.get("sites") or [])
    plans = []
    for term in cfg.get("terms", []):
        for site in sites:
            if site == "naukri":
                plans += [dict(site_name=["naukri"], search_term=term, location=loc) for loc in cfg.get("locations", [])]
            elif site in ("indeed", "glassdoor"):
                plans += [dict(site_name=[site], search_term=term, location=loc, country_indeed="India") for loc in cfg.get("locations", [])]
                if cfg.get("remote"):
                    plans.append(dict(site_name=[site], search_term=term, location="India", is_remote=True, country_indeed="India"))
            elif site == "linkedin":
                plans.append(dict(site_name=["linkedin"], search_term=term, location="India"))
    for p in plans:
        if time.monotonic() > deadline:
            log(f"  radar: time budget reached after {len(rows)} results")
            break
        try:
            df = scrape(results_wanted=int(cfg.get("results_per_query", 40)), hours_old=int(cfg.get("hours_old", 72)), **p)
        except Exception as e:  # a blocked board never stops the scan
            log(f"  radar: {p['site_name'][0]} '{p['search_term']}' failed: {type(e).__name__}")
            continue
        recs = df.to_dict("records") if hasattr(df, "to_dict") else list(df or [])
        rows += recs
    return rows


def harvest(rows: list[dict]) -> dict:
    """{"boards": {(ats, token): {company, site}}, "companies": {name: {site, count}}} from search results."""
    boards: dict[tuple[str, str], dict] = {}
    companies: dict[str, dict] = {}
    for r in rows:
        name = str(r.get("company") or "").strip()
        site = str(r.get("site") or "")
        b = board_from_url(str(r.get("job_url_direct") or "")) or board_from_url(str(r.get("job_url") or ""))
        if b:
            boards.setdefault(b, {"company": name, "site": site})
            continue
        if not name or name.lower() in ("nan", "none") or len(name) < 2 or _AGENCY.search(name):
            continue
        c = companies.setdefault(name, {"site": site, "count": 0})
        c["count"] += 1
    return {"boards": boards, "companies": companies}


def merge(found: dict, cache: dict, csv_path: str | Path, probe: Callable, accept: Callable, now: datetime | None = None) -> dict:
    """Add verified boards to the board map and new company names to the radar list for `discover`."""
    now = now or datetime.now(timezone.utc)
    stamp = now.strftime("%Y-%m-%dT%H:%M:%SZ")
    known = cache.setdefault("companies", {})
    mapped_tokens = {(e.get("ats"), str(e.get("token", "")).lower()) for e in known.values() if e.get("status") == "mapped"}
    added_boards = 0
    for (ats, token), info in found["boards"].items():
        if (ats, token.lower()) in mapped_tokens:
            continue
        name = info["company"] or token
        if known.get(name, {}).get("status") == "mapped":
            continue
        got = probe(ats, token)
        if not got:
            continue
        ok, conf = accept({"name": name, "category": "radar"}, got)
        if not ok and conf != "name-mismatch":
            continue
        # The link came from the employer's own posting, so a name mismatch only means a brand name.
        known[name] = {"status": "mapped", "ats": ats, "token": token, "confidence": f"radar:{conf}", "category": "radar",
                       "boardName": got.get("board_name", ""), "openings": len(got.get("locations", [])), "checkedAt": stamp,
                       "foundVia": info.get("site", "")}
        mapped_tokens.add((ats, token.lower()))
        added_boards += 1
    path = Path(csv_path)
    rows = {}
    if path.exists():
        with path.open(encoding="utf-8", newline="") as f:
            rows = {r["name"]: r for r in csv.DictReader(f)}
    from ..dedupe import company_key
    have = {company_key(n) for n in known} | {company_key(n) for n in rows}
    new_names = 0
    for name, info in sorted(found["companies"].items(), key=lambda x: -x[1]["count"]):
        if company_key(name) in have:
            continue
        rows[name] = {"name": name, "category": "radar", "city": "", "website": "", "slugs": " ".join(slugs_for(name)),
                      "ats": "", "token": "", "source": f"radar:{info['site']} {stamp[:10]}"}
        have.add(company_key(name))
        new_names += 1
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["name", "category", "city", "website", "slugs", "ats", "token", "source"])
        w.writeheader()
        for r in rows.values():
            w.writerow({k: r.get(k, "") for k in w.fieldnames})
    return {"boardsAdded": added_boards, "companiesAdded": new_names, "radarCompanies": len(rows)}
