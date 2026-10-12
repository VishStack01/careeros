"""Build the public job board from the feed: a static site for GitHub Pages.

  careeros site --feed feed --out site [--demo dashboard/index.html]

Output:
  index.html               the board (search, filters, job pages, companies)
  data/jobs.json           every open role, compact, for the board
  data/jobs/<id>.json      one role with the full posting and the quoted facts
  api/jobs.json            public JSON API, 100 roles per page, Arbeitnow-style
  api/jobs/page-<n>.json   further pages
  feed.xml                 RSS of the 100 newest roles
  demo/index.html          the dashboard demo (fictional data), if given

The board holds only public job postings. Nothing about any job seeker is in it.
"""

from __future__ import annotations

import gzip
import json
import re
import shutil
from datetime import datetime, timezone
from email.utils import format_datetime
from pathlib import Path
from xml.sax.saxutils import escape

from . import tags as tagger
from .models import iso

HERE = Path(__file__).resolve().parent
TEMPLATE = HERE / "site_app.html"
PER_PAGE = 100
MAX_AGE_DAYS = 60  # older listings are usually evergreen or forgotten; the board leaves them out
# Where a role can be done from, as shown on the board (see scan.loc_class).
WHERE = {"remote-worldwide": "ww", "remote-open": "ro", "remote-india": "ri", "remote-unclear": "ru",
         "remote-excluded": "rx", "south": "s", "india": "i", "abroad": "a", "unknown": "u"}


def _read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with gzip.open(path, "rt", encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def _salary(r: dict) -> str:
    if r.get("salary"):
        return r["salary"]
    f = r.get("facts") or {}
    hi, lo = f.get("salaryHigh"), f.get("salaryLow")
    if hi is None:
        return ""
    fmt = lambda x: f"{x:.1f}".rstrip("0").rstrip(".")
    return f"{fmt(lo)}–{fmt(hi)} LPA" if lo and lo != hi else f"{fmt(hi)} LPA"


def _slug(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", (s or "").lower()).strip("-")[:80]


def compact(r: dict) -> dict:
    f = r.get("facts") or {}
    t = r.get("tags") or tagger.tag(r.get("title", ""), r.get("summary", ""), f)  # feeds written before tags existed
    return {
        "id": r["id"], "t": r["title"], "c": r["company"], "cs": _slug(r["company"]), "l": r.get("location", ""),
        "m": r.get("workMode", ""), "w": WHERE.get(f.get("loc", ""), "u" if "loc" not in f else ""), "p": r.get("postedAt", ""),
        "sal": _salary(r), "e": f.get("expMin"), "lv": t.get("level", ""), "ty": t.get("type", ""),
        "cat": t.get("categories", []), "sk": t.get("skills", []), "pk": t.get("perks", []),
        "src": r.get("source", ""), "via": r.get("via", ""), "u": r["url"],
    }


def detail(r: dict, text: str) -> dict:
    f = r.get("facts") or {}
    facts = []
    exp = f.get("expMin")
    facts.append({"k": "Experience", "v": ("Fresher welcome" if f.get("fresherOk") else "Not stated") if exp is None
                  else ("Fresher (0 years)" if exp == 0 else f"{exp:g}+ years"), "q": f.get("expQuote") or ""})
    who = {"ww": "Remote, anywhere in the world", "ro": "Remote, open to India", "ri": "Remote within India",
           "ru": "Remote; the posting doesn't say who can apply", "rx": "Remote, but not open to people in India",
           "s": "On-site or hybrid in south India", "i": "On-site or hybrid in India", "a": "On-site or hybrid abroad",
           "u": "Not stated"}.get(compact(r)["w"], "Not stated")
    facts.append({"k": "Where", "v": who, "q": f.get("locQuote") or f.get("scopeQuote") or ""})
    sal = _salary(r)
    facts.append({"k": "Pay", "v": sal or "Not stated", "q": f.get("salaryQuote") or ""})
    if f.get("closedQuote"):
        facts.append({"k": "Status", "v": "The posting says it's closed", "q": f["closedQuote"]})
    if f.get("applicants"):
        facts.append({"k": "Applicants", "v": str(f["applicants"]), "q": ""})
    return compact(r) | {"text": text, "facts": facts, "hq": r.get("hq", ""), "category": r.get("category", "")}


def api_item(r: dict, text: str) -> dict:
    c = compact(r)
    return {"slug": r["id"], "company_name": r["company"], "title": r["title"], "description": text,
            "remote": c["m"] == "remote", "url": r["url"], "tags": c["cat"] + c["sk"], "job_types": [c["ty"]] if c["ty"] else [],
            "level": c["lv"], "location": r.get("location", ""), "where": c["w"], "salary": c["sal"],
            "experience_min_years": c["e"], "source": r.get("source", ""), "created_at": r.get("postedAt", "")}


def _rss(jobs: list[dict], base_url: str, now: datetime) -> str:
    items = []
    for r in jobs[:100]:
        try:
            pub = format_datetime(datetime.fromisoformat(r["postedAt"].replace("Z", "+00:00")))
        except (ValueError, KeyError, AttributeError, TypeError):
            pub = format_datetime(now)
        link = f"{base_url}#/job/{r['id']}" if base_url else r["url"]
        desc = " · ".join(x for x in (r["company"], r.get("location", ""), _salary(r)) if x)
        items.append(f"<item><title>{escape(r['title'] + ' at ' + r['company'])}</title><link>{escape(link)}</link>"
                     f"<guid isPermaLink=\"false\">{escape(r['id'])}</guid><pubDate>{pub}</pubDate><description>{escape(desc)}</description></item>")
    return ('<?xml version="1.0" encoding="UTF-8"?>\n<rss version="2.0"><channel><title>CareerOS Jobs</title>'
            f"<link>{escape(base_url or 'https://github.com/VishStack01/careeros')}</link>"
            "<description>Open tech roles in India and remote, straight from company career pages.</description>"
            f"<lastBuildDate>{format_datetime(now)}</lastBuildDate>" + "".join(items) + "</channel></rss>\n")


def build(feed_dir: str | Path, out_dir: str | Path, demo: str | Path | None = None, base_url: str = "", log=print) -> dict:
    feed_dir, out = Path(feed_dir), Path(out_dir)
    records = _read_jsonl(feed_dir / "india.jsonl.gz")
    texts = {t["id"]: t.get("text", "") for t in _read_jsonl(feed_dir / "full.jsonl.gz")}
    summary = json.loads((feed_dir / "summary.json").read_text()) if (feed_dir / "summary.json").exists() else {}
    now = datetime.now(timezone.utc)
    if out.exists():
        shutil.rmtree(out)
    (out / "data" / "jobs").mkdir(parents=True)
    (out / "api" / "jobs").mkdir(parents=True)

    def age_days(r):
        try:
            d = datetime.fromisoformat((r.get("postedAt") or "").replace("Z", "+00:00"))
            return (now - (d if d.tzinfo else d.replace(tzinfo=timezone.utc))).days
        except ValueError:
            return 0
    records = [r for r in records if age_days(r) <= MAX_AGE_DAYS and not (r.get("facts") or {}).get("closedQuote")]
    records.sort(key=lambda r: r.get("postedAt") or "", reverse=True)
    compacts = [compact(r) for r in records]
    companies: dict[str, dict] = {}
    for c in compacts:
        e = companies.setdefault(c["cs"], {"name": c["c"], "slug": c["cs"], "jobs": 0})
        e["jobs"] += 1
    meta = {"generatedAt": iso(now), "feedAt": summary.get("generatedAt", ""), "jobs": len(compacts),
            "companyBoards": summary.get("boards", 0), "companiesTracked": summary.get("companies", 0),
            "remoteBoards": len(summary.get("remoteBoards") or {}), "companies": len(companies)}
    (out / "data" / "jobs.json").write_text(json.dumps({"meta": meta, "jobs": compacts}, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    (out / "data" / "companies.json").write_text(json.dumps(sorted(companies.values(), key=lambda x: (-x["jobs"], x["name"].lower())),
                                                            ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    for r in records:
        text = texts.get(r["id"]) or r.get("summary", "")
        (out / "data" / "jobs" / f"{r['id']}.json").write_text(json.dumps(detail(r, text), ensure_ascii=False, separators=(",", ":")), encoding="utf-8")

    pages = max(1, -(-len(records) // PER_PAGE))
    for n in range(1, pages + 1):
        chunk = records[(n - 1) * PER_PAGE: n * PER_PAGE]
        link = lambda k: f"{base_url}api/jobs/page-{k}.json" if 1 <= k <= pages else None
        body = {"data": [api_item(r, texts.get(r["id"]) or r.get("summary", "")) for r in chunk],
                "links": {"first": link(1), "last": link(pages), "prev": link(n - 1), "next": link(n + 1)},
                "meta": {"current_page": n, "last_page": pages, "per_page": PER_PAGE, "total": len(records), "generated_at": meta["generatedAt"]}}
        payload = json.dumps(body, ensure_ascii=False, separators=(",", ":"))
        (out / "api" / "jobs" / f"page-{n}.json").write_text(payload, encoding="utf-8")
        if n == 1:
            (out / "api" / "jobs.json").write_text(payload, encoding="utf-8")
    (out / "feed.xml").write_text(_rss(records, base_url, now), encoding="utf-8")
    (out / "index.html").write_text(TEMPLATE.read_text(encoding="utf-8"), encoding="utf-8")
    (out / ".nojekyll").write_text("")
    if demo and Path(demo).exists():
        (out / "demo").mkdir()
        shutil.copy(demo, out / "demo" / "index.html")
    log(f"Job board: {len(records)} roles, {len(companies)} companies, {pages} API pages -> {out}")
    return meta
