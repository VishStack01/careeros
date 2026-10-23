"""Public entry-level pay data (config/pay/entry-pay.csv): an estimate for roles that don't state pay."""

from __future__ import annotations

import csv
from functools import lru_cache
from pathlib import Path

from .dedupe import company_key

DEFAULT = Path(__file__).resolve().parent.parent / "config" / "pay" / "entry-pay.csv"
SOURCES = {
    "250cl": ("250CompanyList", "https://github.com/KushalVijay/250CompanyList"),
    "jobrise": ("Jobrise 2026", "https://jobrise.io/en/blog/top-paying-companies-india-2026/"),
}


@lru_cache(maxsize=4)
def load(path: str | None = None) -> dict[str, dict]:
    p = Path(path) if path else DEFAULT
    out: dict[str, dict] = {}
    if not p.exists():
        return out
    with p.open(encoding="utf-8", newline="") as f:
        for r in csv.DictReader(f):
            try:
                band = {"low": float(r["low_lpa"]), "high": float(r["high_lpa"]), "basis": r.get("basis", ""),
                        "source": " · ".join(SOURCES.get(s, (s, ""))[0] for s in (r.get("sources") or "").split(";") if s),
                        "url": next((SOURCES[s][1] for s in (r.get("sources") or "").split(";") if s in SOURCES), "")}
            except (KeyError, ValueError):
                continue
            for name in [r["company"]] + [a for a in (r.get("aliases") or "").split(";") if a.strip()]:
                k = company_key(name)
                if k:
                    out[k] = band
    return out


def band(company: str, path: str | None = None) -> dict | None:
    """{low, high, basis, source, url} for this company, or None."""
    return load(path).get(company_key(company or ""))


def describe(b: dict) -> str:
    lo, hi = b["low"], b["high"]
    rng = f"{lo:g}" if lo == hi else f"{lo:g}–{hi:g}"
    return f"{rng} LPA for freshers ({b['basis']}, {b['source']})"
