"""Companies that just raised money: they hire next, often before the roles reach job boards.

    careeros funded [--days 30] [--json]          read the funding news feeds, list new companies
    careeros funded --add "Name One,Name Two"     add the ones you choose to companies.csv

Reads public RSS feeds (Inc42, Entrackr, TechCrunch's India and venture tags by
default) and pulls out "X raises $5 Mn in Series A" headlines. Review-first: it
lists candidates with the article they came from and adds nothing until you
name them. `careeros discover` then finds each new company's job board.
"""

from __future__ import annotations

import csv
import re
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path

from .dedupe import company_key

FEEDS = [
    "https://inc42.com/buzz/feed/",
    "https://inc42.com/feed/",
    "https://entrackr.com/feed/",
    "https://techcrunch.com/tag/india/feed/",
]

_VERB = r"(?:raises|raised|bags|secures|secured|gets|closes|nets|lands|picks up|mops up|garners|scoops up|rakes in)"
_PREFIX = re.compile(r"^(?:exclusive|funding alert|breaking)\s*[:|-]\s*|^(?:[A-Z][\w&.-]*(?:\s[A-Z][\w&.-]*)?)-based\s+|"
                     r"^(?:[a-z0-9]+(?:\s[a-z0-9]+)?\s)?(?:startup|platform|company|unicorn|major|player|app|maker|firm|brand|marketplace)\s+", re.I)
_DESCRIPTOR = re.compile(r"^(?:(?:ai|saas|fintech|edtech|healthtech|agritech|d2c|ev|deeptech|insurtech|proptech|logistics|b2b|b2c|gaming|"
                         r"spacetech|climate ?tech|cleantech|web3|crypto|quick commerce|social commerce|e-?commerce|mobility|robotics|"
                         r"cybersecurity|hr ?tech|legaltech|foodtech|traveltech|media|beauty|fashion)\s+)+(?:startup|platform|company|firm|brand|player|marketplace)?\s*", re.I)
_AMOUNT = re.compile(r"((?:\$|usd|inr|rs\.?|₹)\s?[\d.,]+\s?(?:mn|million|m|bn|billion|cr|crore|lakh|k)?|[\d.,]+\s?(?:mn|million|bn|billion|cr|crore)\b)", re.I)
_ROUND = re.compile(r"\b(pre-?seed|seed|angel|pre-?series [a-f]|series [a-f]\d?|bridge|debt|growth|venture debt|ipo)\b", re.I)


def headline(title: str) -> dict | None:
    """{company, amount, round} from a funding headline, or None."""
    t = re.sub(r"\s+", " ", title or "").strip()
    m = re.match(rf"(.{{2,80}}?)\s+{_VERB}\b(.*)$", t, re.I)
    if not m:
        return None
    rest = m.group(2)
    if not _AMOUNT.search(rest) and not re.search(r"\b(funding|round|investment)\b", rest, re.I):
        return None
    name = m.group(1).strip(" '\"‘’“”")
    for _ in range(3):
        name = _PREFIX.sub("", name).strip()
        name = _DESCRIPTOR.sub("", name).strip()
    name = re.sub(r"^(?:the|india's|indian)\s+", "", name, flags=re.I).strip(" ,:")
    if not name or len(name) > 40 or len(name.split()) > 4 or re.search(r"\b(startups|companies|roundup|weekly|funding)\b", name, re.I):
        return None
    amt = _AMOUNT.search(rest)
    rnd = _ROUND.search(rest)
    return {"company": name, "amount": amt.group(1).strip() if amt else "", "round": rnd.group(1).title() if rnd else ""}


def parse_feed(xml: bytes | str) -> list[dict]:
    """RSS or Atom items: {title, link, date}."""
    try:
        root = ET.fromstring(xml)
    except ET.ParseError:
        return []
    out = []
    for it in root.iter():
        tag = it.tag.split("}")[-1]
        if tag not in ("item", "entry"):
            continue
        get = lambda n: next((c for c in it if c.tag.split("}")[-1] == n), None)
        title = (get("title").text or "") if get("title") is not None else ""
        link_el = get("link")
        link = (link_el.text or link_el.get("href") or "") if link_el is not None else ""
        d = get("pubDate") if get("pubDate") is not None else get("published") if get("published") is not None else get("updated")
        date = ""
        if d is not None and d.text:
            try:
                date = parsedate_to_datetime(d.text).astimezone(timezone.utc).isoformat()
            except (TypeError, ValueError):
                date = d.text.strip()
        out.append({"title": title.strip(), "link": link.strip(), "date": date})
    return out


def known_keys(companies_csv: str | Path) -> set[str]:
    p = Path(companies_csv)
    if not p.exists():
        return set()
    with p.open(encoding="utf-8") as f:
        return {company_key(r.get("name", "")) for r in csv.DictReader(f)}


def candidates(items: list[dict], known: set[str], days: int = 30, now: datetime | None = None) -> list[dict]:
    now = now or datetime.now(timezone.utc)
    seen: dict[str, dict] = {}
    for it in items:
        try:
            when = datetime.fromisoformat(it["date"])
            if now - when > timedelta(days=days):
                continue
        except (KeyError, ValueError):
            pass
        h = headline(it.get("title", ""))
        if not h:
            continue
        k = company_key(h["company"])
        if not k or k in seen:
            continue
        seen[k] = dict(h, source=it.get("link", ""), headline=it.get("title", ""), date=it.get("date", "")[:10], tracked=k in known)
    return sorted(seen.values(), key=lambda c: (c["tracked"], c["date"]), reverse=False)


def fetch(feeds: list[str] = FEEDS, timeout: int = 20) -> tuple[list[dict], list[str]]:
    items, errors = [], []
    for url in feeds:
        try:
            raw = urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "careeros (+https://github.com)"}), timeout=timeout).read()
            items += parse_feed(raw)
        except OSError as e:
            errors.append(f"{url}: {e}")
    return items, errors


def add(names: list[str], found: list[dict], companies_csv: str | Path) -> list[str]:
    """Append the named candidates to companies.csv (source "funded"). Returns the names added."""
    p = Path(companies_csv)
    known = known_keys(p)
    by_key = {company_key(c["company"]): c for c in found}
    added = []
    with p.open("a", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        for n in names:
            k = company_key(n)
            if not k or k in known:
                continue
            c = by_key.get(k, {"company": n.strip()})
            w.writerow([c["company"], "funded", "", "", "", "", "", f"funded {c.get('round', '')} {c.get('date', '')}".strip()])
            known.add(k)
            added.append(c["company"])
    return added
