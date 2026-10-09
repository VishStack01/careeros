"""Build config/companies/companies.csv from the curated list and the public YC dataset.

  python scripts/build_company_list.py [--yc path/to/yc_all.json]

The YC dataset is https://github.com/yc-oss/api (companies/all.json). We take
active companies located in India, plus YC companies that are hiring and list
remote work. Board slugs come from the name, the website domain and any aliases.
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import urllib.request
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
CURATED = ROOT / "config" / "companies" / "curated.txt"
OUT = ROOT / "config" / "companies" / "companies.csv"
YC_URL = "https://raw.githubusercontent.com/yc-oss/api/main/companies/all.json"


def norm(name: str) -> str:
    n = re.sub(r"\b(ai|labs?|technologies|technology|inc|pvt|ltd|private|limited|india|hq|app|the)\b", " ", name.lower())
    return re.sub(r"[^a-z0-9]", "", n) or re.sub(r"[^a-z0-9]", "", name.lower())


def slugs_for(name: str, website: str = "", aliases: list[str] | None = None) -> list[str]:
    base = name.lower().replace("&", "and")
    out = [re.sub(r"[^a-z0-9]", "", base), re.sub(r"[^a-z0-9]+", "-", base).strip("-")]
    host = urlparse(website if "://" in website else f"https://{website}").netloc.lower().removeprefix("www.") if website else ""
    if host:
        out.append(host.split(".")[0])
    out += [a.strip().lower() for a in (aliases or []) if a.strip()]
    seen, res = set(), []
    for s in out:
        if s and s not in seen and len(s) >= 2:
            seen.add(s)
            res.append(s)
    return res


def load_curated() -> list[dict]:
    rows, cat = [], ""
    for line in CURATED.read_text(encoding="utf-8").splitlines():
        s = line.strip()
        if s.startswith("## "):
            cat = s[3:].strip()
            continue
        if not s or s.startswith("#"):
            continue
        parts = [p.strip() for p in s.split("|")] + ["", "", ""]
        name, aliases, city, known = parts[0], parts[1], parts[2], parts[3]
        ats, token = (known.split(":", 1) + [""])[:2] if known else ("", "")
        rows.append({"name": name, "category": cat, "city": city, "website": "",
                     "slugs": slugs_for(name, "", aliases.split(",") if aliases else []),
                     "ats": ats, "token": token, "source": "curated"})
    return rows


def load_yc(path: str | None) -> list[dict]:
    data = json.loads(Path(path).read_text()) if path else json.load(urllib.request.urlopen(YC_URL, timeout=60))
    rows = []
    for c in data:
        status = (c.get("status") or "").lower()
        if status not in ("active", "public"):
            continue
        locs = (c.get("all_locations") or "")
        regions = " ".join(c.get("regions") or [])
        in_india = "india" in locs.lower() or "india" in regions.lower()
        remote_hiring = bool(c.get("isHiring")) and "remote" in (locs + " " + regions).lower()
        if not (in_india or remote_hiring):
            continue
        city = locs.split(",")[0].strip() if in_india else "Remote"
        rows.append({"name": c["name"].strip(), "category": "yc-india" if in_india else "yc-remote", "city": city,
                     "website": c.get("website") or "", "slugs": slugs_for(c["name"], c.get("website") or "", [c.get("slug") or ""]),
                     "ats": "", "token": "", "source": f"yc:{c.get('batch', '')}"})
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--yc", help="Local copy of the YC companies JSON")
    ap.add_argument("--max-yc-remote", type=int, default=150)
    a = ap.parse_args()
    rows = load_curated()
    seen = {norm(r["name"]) for r in rows}
    yc = load_yc(a.yc)
    yc.sort(key=lambda r: (r["category"] != "yc-india", r["name"].lower()))
    remote_added = 0
    for r in yc:
        k = norm(r["name"])
        if k in seen:
            continue
        if r["category"] == "yc-remote":
            if remote_added >= a.max_yc_remote:
                continue
            remote_added += 1
        seen.add(k)
        rows.append(r)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["name", "category", "city", "website", "slugs", "ats", "token", "source"])
        for r in rows:
            w.writerow([r["name"], r["category"], r["city"], r["website"], " ".join(r["slugs"]), r["ats"], r["token"], r["source"]])
    cats = {}
    for r in rows:
        cats[r["category"]] = cats.get(r["category"], 0) + 1
    print(f"wrote {OUT} with {len(rows)} companies")
    for k, v in sorted(cats.items(), key=lambda x: -x[1]):
        print(f"  {k:36} {v}")


if __name__ == "__main__":
    main()
