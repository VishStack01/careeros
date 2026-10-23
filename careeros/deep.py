"""Deep sweep: company job boards that almost nobody searches.

    careeros deep --boards feed/boards.json --out feed/deep-companies.csv

Most job seekers only see what reaches LinkedIn, Naukri and Indeed. Thousands
of startups post only on their own Greenhouse, Lever, Ashby, Workable,
SmartRecruiters or Recruitee board, and most large employers on Workday. The open-source ats-scrapers project
(MIT, github.com/kalil0321/ats-scrapers) keeps an inventory of about 24,000
such boards. This command downloads that inventory, drops the boards CareerOS
already knows, and writes the rest as a company list for `careeros discover`.

`discover` then checks each board once (about 400 an hour, so the first pass
takes about two days) and keeps it only when it lists a developer-side role in
India or open to people in India. The others are looked at again after three
weeks. Kept boards join the hourly scan like any other company board, so their
roles go through the same checks, and Ashby, Lever and Greenhouse boards bring
their published pay ranges with them.
"""

from __future__ import annotations

import csv
import io
from pathlib import Path
from typing import Callable

from .dedupe import company_key
from .sources import http

INVENTORY = "https://raw.githubusercontent.com/kalil0321/ats-scrapers/main/ats-companies/{ats}.csv"
# Startups that publish pay most often first: Ashby and Lever carry structured pay fields.
ATS = ["ashby", "lever", "greenhouse", "workday", "workable", "smartrecruiters", "recruitee"]
FIELDS = ["name", "category", "city", "website", "slugs", "ats", "token", "source"]


def parse(ats: str, text: str) -> list[dict]:
    from .sources.workday import token_from_url
    rows = []
    for r in csv.DictReader(io.StringIO(text)):
        name, slug = (r.get("name") or "").strip(), (r.get("slug") or "").strip()
        if ats == "workday":  # the token needs the wdN host from the URL
            slug = token_from_url(r.get("url") or "") or ""
            ok = bool(slug)
        else:
            ok = bool(slug) and "/" not in slug
        if name and ok and len(slug) <= 120:
            rows.append({"name": name, "ats": ats, "token": slug})
    return rows


def fetch(ats_list: list[str] = ATS, get: Callable[[str], str] | None = None, log=print) -> list[dict]:
    get = get or (lambda url: http.get_text(url, timeout=60, retries=2))
    rows: list[dict] = []
    for ats in ats_list:
        try:
            got = parse(ats, get(INVENTORY.format(ats=ats)))
        except Exception as e:  # one missing list never stops the others
            log(f"  deep: {ats} inventory unavailable ({type(e).__name__})")
            continue
        log(f"  deep: {len(got)} {ats} boards in the inventory")
        rows += got
    return rows


def build(rows: list[dict], cache: dict) -> list[dict]:
    """Inventory rows CareerOS doesn't know yet, as company-list rows for discover."""
    # Boards found by the curated list or the hiring radar stay theirs; boards found by an
    # earlier sweep stay on this list so discover keeps re-checking them.
    known = {n: e for n, e in cache.get("companies", {}).items() if e.get("category") != "deep"}
    tokens = {(e.get("ats"), str(e.get("token", "")).lower()) for e in known.values() if e.get("token")}
    names = {company_key(n) for n in known}
    out, seen = [], set()
    for r in rows:
        tok = (r["ats"], r["token"].lower())
        key = company_key(r["name"])
        if tok in tokens or tok in seen or not key or key in names:
            continue
        seen.add(tok)
        out.append({"name": r["name"], "category": "deep", "city": "", "website": "", "slugs": "",
                    "ats": r["ats"], "token": r["token"], "source": "ats-scrapers (MIT)"})
    return out


def write(rows: list[dict], path: str | Path) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in FIELDS})


def stats(cache: dict) -> dict:
    deep = [e for e in cache.get("companies", {}).values() if e.get("category") == "deep"]
    return {"checked": sum(1 for e in deep if e.get("checkedAt")),
            "mapped": sum(1 for e in deep if e.get("status") == "mapped")}
