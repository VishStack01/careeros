"""careeros command line.

  careeros init                         copy example configs into place
  careeros scout                        poll the watchlist, gate every role, store results
  careeros evaluate --title ... --text-file posting.txt [--save]
                                        run the gates on a posting found elsewhere (agent use)
  careeros list [--stage found]         show roles
  careeros show ID                      show one role with every check and its quote
  careeros brain-check [PATH]           find claims that can't reach a resume yet
  careeros claims-check RESUME.json     block resume lines the brain can't back up
  careeros apply URL --job-id ID --package PKG.json [--submit]
                                        fill an application form; submit only if safe
  careeros pause | resume               kill switch for all submissions
  careeros serve [--port 8765]          open the dashboard locally

India feed (runs on GitHub Actions; see .github/workflows/scan.yml):
  careeros discover                     find each company's public job board
  careeros scan                         read every mapped board, write feed/india.jsonl.gz
  careeros filter-feed --feed URL --settings-json S.json --known DIR --out DIR
                                        apply your filters to the feed (agent use)
  careeros platforms [--run N] [--json] job platforms for the agent to visit this run
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

from . import __version__, brain, claims, pipeline
from .gates import apply_decision
from .models import REGIONS, Job, iso
from .settings import Settings
from .store import Store

ROOT = Path.cwd()


def _settings_doc(s: Settings) -> dict:
    """The settings shape the dashboard displays."""
    exp = ["Fresher"] + ([f"{int(s.max_required_years)}+ years"] if s.max_required_years >= 1 else [])
    locs = []
    if s.location.south_india != "never":
        locs.append("South India (any work mode)" if s.location.south_india == "any" else "South India (remote only)")
    if s.location.rest_of_india != "never":
        locs.append("Rest of India (remote only)" if s.location.rest_of_india == "remote" else "Rest of India (any work mode)")
    if s.location.abroad != "never":
        locs.append("Remote worldwide (first priority)")
    return {
        "experienceLevels": exp, "maxRequiredYears": s.max_required_years, "maxPostingAgeDays": s.max_posting_age_days,
        "locations": locs, "salaryFloorLpa": s.salary_floor_lpa if s.salary_floor_lpa is not None else "",
        "dailyCap": s.daily_cap, "approvalMode": "auto-when-clear", "updatedAt": iso(datetime.now(timezone.utc)),
    }


def cmd_init(a):
    pairs = [
        ("config/settings.example.toml", "config/settings.toml"),
        ("config/watchlist.example.toml", "config/watchlist.toml"),
        ("config/profile.example.toml", "config/profile.toml"),
        ("brain/brain.example.json", "brain/brain.json"),
    ]
    for src, dst in pairs:
        if Path(dst).exists():
            print(f"kept     {dst}")
        elif Path(src).exists():
            shutil.copy(src, dst)
            print(f"created  {dst}")
    print("\nNext: edit config/profile.toml and brain/brain.json with your real details, then run `careeros scout`.")


def cmd_scout(a):
    s = Settings.load(a.settings)
    store = Store(a.db)
    store.set("settings", "profile", _settings_doc(s) | {"schedule": a.schedule or ""})
    boards = pipeline.load_watchlist(a.watchlist)
    rep = pipeline.run(store, s, boards, record_skips=not a.no_skips)
    print(rep.summary())
    for k in rep.kept[:10]:
        flag = "  NEW <48h" if k["priority"] else ""
        print(f"  [{k['region']}] {k['title']} at {k['company']}{flag}")
    for e in rep.errors:
        print(f"  ! {e}", file=sys.stderr)


def cmd_evaluate(a):
    s = Settings.load(a.settings)
    text = Path(a.text_file).read_text(encoding="utf-8") if a.text_file else (a.text or "")
    job = Job(company=a.company, title=a.title, url=a.url or "", source=a.source or "manual", location=a.location or "",
              work_mode=a.mode or "", description=text, posted_at=a.posted or "", apply_by=a.apply_by or "",
              salary_text=a.salary or "", raw={"experience_header": a.experience_header or ""})
    d = apply_decision(job, s)
    out = {"kept": d.kept, "region": d.region, "priority": d.priority, "checks": [c.to_dict() for c in d.checks]}
    if a.save:
        status, doc_id = Store(a.db).add_job(job)
        out["saved"] = {"status": status, "id": doc_id}
    print(json.dumps(out, indent=2, ensure_ascii=False))


def cmd_list(a):
    docs = Store(a.db).list("jobs")
    if a.stage:
        docs = [d for d in docs if d["data"].get("stage") == a.stage]
    docs.sort(key=lambda d: (REGIONS.get(d["data"].get("region", ""), 9), d["data"].get("postedAt", "")), reverse=False)
    for d in docs:
        j = d["data"]
        print(f"{j.get('stage', ''):9} {j.get('region', '') or '-':14} {j.get('title', '')[:48]:48} {j.get('company', '')[:24]:24} {d['id']}")
    print(f"\n{len(docs)} role(s)")


def cmd_show(a):
    doc = Store(a.db).get("jobs", a.id)
    if not doc:
        sys.exit(f"No role with id {a.id}")
    j = doc["data"]
    print(f"{j['title']} at {j['company']}\n{j.get('url', '')}\nStage: {j.get('stage')}  Region: {j.get('region') or '-'}\n")
    for c in j.get("checks", []):
        mark = "PASS" if c["passed"] else "FAIL"
        print(f"  {mark}  {c['gate']:<12} {c['value']}")
        if c.get("quote"):
            print(f"        \"{c['quote']}\"")


def cmd_brain_check(a):
    problems = brain.validate(brain.load(a.path))
    if not problems:
        print("Brain looks good: every claim has evidence.")
        return
    print(f"{len(problems)} problem(s):")
    for p in problems:
        print(f"  - {p}")
    sys.exit(1)


def cmd_claims_check(a):
    rep = claims.check(json.loads(Path(a.resume).read_text(encoding="utf-8")), brain.load(a.brain))
    for b in rep.blocking:
        print(f"BLOCK  {b}")
    for w in rep.warnings:
        print(f"WARN   {w}")
    print(f"\nMetric density: {rep.metric_density:.0%}. {'OK to send.' if rep.ok else 'Blocked: fix the lines above.'}")
    sys.exit(0 if rep.ok else 1)


def cmd_apply(a):
    from .apply import runner
    from .apply.answers import Context

    store = Store(a.db)
    job = (store.get("jobs", a.job_id) or {}).get("data", {}) if a.job_id else {}
    package = json.loads(Path(a.package).read_text(encoding="utf-8")) if a.package else {}
    ctx = Context.load(a.profile, a.brain, package, job | {"url": a.url})
    res = runner.run(a.url, ctx, submit=a.submit, store=store, job_id=a.job_id or "", receipts_dir=a.receipts, headed=a.headed)
    print(f"Status: {res.status}   Receipt: {res.receipt_dir}")
    for r in res.resolutions:
        if r["confidence"] != "skip":
            print(f"  {r['confidence']:8} {r['label'][:60]:60} -> {str(r['value'])[:40]}")
    for b in res.blockers:
        print(f"  STOP   {b}")
    for n in res.needs_you:
        print(f"  NEEDS YOU  {n}")
    for e in res.errors:
        print(f"  ERROR  {e}")
    if res.status == "applied" and a.job_id and store.get("jobs", a.job_id):
        stamp = iso(datetime.now(timezone.utc))
        cur = store.get("jobs", a.job_id)["data"]
        store.update("jobs", a.job_id, {"stage": "applied", "appliedAt": stamp, "appliedVia": "careeros",
                                        "timeline": cur.get("timeline", []) + [{"at": stamp, "event": "Applied; confirmation captured"}]})


def cmd_pause(a):
    Store(a.db).set_flag("paused", True)
    print("Paused. No application will be submitted until you run `careeros resume`.")


def cmd_resume(a):
    Store(a.db).set_flag("paused", False)
    print("Resumed.")


def cmd_discover(a):
    from . import discover
    discover.run(a.companies, a.cache, refresh_days=a.refresh_days, workers=a.workers, limit=a.limit)


def cmd_scan(a):
    from . import scan
    scan.run(a.boards, a.out, workers=a.workers, detail_cap=a.detail_cap, aggregators=not a.no_remote_boards)


def cmd_filter_feed(a):
    from . import feed
    if a.settings_json:
        doc = json.loads(Path(a.settings_json).read_text(encoding="utf-8"))
        doc = doc.get("data", doc) if isinstance(doc, dict) else doc
        s = feed.settings_from_dashboard(doc)
    else:
        s = Settings.load(a.settings)
    idx = feed.run(a.feed, s, a.known, a.out, max_skips=a.max_skips, max_kept=a.max_kept)
    print(json.dumps({k: (len(v) if isinstance(v, list) and k in ("kept", "skipped") else v) for k, v in idx.items()}, indent=2))


def cmd_platforms(a):
    from . import platforms
    ps = platforms.load(a.file)
    todo = ps if a.all else platforms.for_run(ps, a.run)
    if a.json:
        print(json.dumps({"summary": platforms.summary(ps), "thisRun": todo}, indent=2, ensure_ascii=False))
        return
    for p in todo:
        print(f"{p['competition']:6} {p['access']:6} {p['name'][:44]:44} {p['url']}")
    print(f"\n{len(todo)} of {len(ps)} platforms")


def cmd_serve(a):
    from .server import serve
    serve(Store(a.db), Path(a.root), a.port)


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(prog="careeros", description="Evidence-first job application agent.")
    p.add_argument("--version", action="version", version=f"careeros {__version__}")
    p.add_argument("--db", default="data/careeros.db", help="SQLite file (default: data/careeros.db)")
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("init").set_defaults(fn=cmd_init)

    sp = sub.add_parser("scout")
    sp.add_argument("--watchlist", default="config/watchlist.toml")
    sp.add_argument("--settings", default="config/settings.toml")
    sp.add_argument("--schedule", default="", help="Shown on the dashboard, e.g. 'every 3 hours'")
    sp.add_argument("--no-skips", action="store_true", help="Don't log skipped roles")
    sp.set_defaults(fn=cmd_scout)

    sp = sub.add_parser("evaluate")
    sp.add_argument("--company", required=True)
    sp.add_argument("--title", required=True)
    sp.add_argument("--location")
    sp.add_argument("--mode", choices=["remote", "hybrid", "onsite", ""])
    sp.add_argument("--posted", help="ISO date the role was posted")
    sp.add_argument("--apply-by")
    sp.add_argument("--salary")
    sp.add_argument("--experience-header", help="Experience as shown on the job card, e.g. '1 year(s)'")
    sp.add_argument("--text-file")
    sp.add_argument("--text")
    sp.add_argument("--url")
    sp.add_argument("--source")
    sp.add_argument("--settings", default="config/settings.toml")
    sp.add_argument("--save", action="store_true")
    sp.set_defaults(fn=cmd_evaluate)

    sp = sub.add_parser("list")
    sp.add_argument("--stage")
    sp.set_defaults(fn=cmd_list)

    sp = sub.add_parser("show")
    sp.add_argument("id")
    sp.set_defaults(fn=cmd_show)

    sp = sub.add_parser("brain-check")
    sp.add_argument("path", nargs="?", default="brain/brain.json")
    sp.set_defaults(fn=cmd_brain_check)

    sp = sub.add_parser("claims-check")
    sp.add_argument("resume")
    sp.add_argument("--brain", default="brain/brain.json")
    sp.set_defaults(fn=cmd_claims_check)

    sp = sub.add_parser("apply")
    sp.add_argument("url")
    sp.add_argument("--job-id", default="")
    sp.add_argument("--package", help="JSON: {resume, cover_note, answers: {question: answer}}")
    sp.add_argument("--profile", default="config/profile.toml")
    sp.add_argument("--brain", default="brain/brain.json")
    sp.add_argument("--receipts", default="receipts")
    sp.add_argument("--submit", action="store_true", help="Actually submit when every required answer is covered")
    sp.add_argument("--headed", action="store_true", help="Show the browser window")
    sp.set_defaults(fn=cmd_apply)

    sub.add_parser("pause").set_defaults(fn=cmd_pause)
    sub.add_parser("resume").set_defaults(fn=cmd_resume)

    sp = sub.add_parser("discover", help="Find public job boards for the company list")
    sp.add_argument("--companies", default="config/companies/companies.csv")
    sp.add_argument("--cache", default="feed/boards.json")
    sp.add_argument("--refresh-days", type=int, default=14)
    sp.add_argument("--workers", type=int, default=32)
    sp.add_argument("--limit", type=int)
    sp.set_defaults(fn=cmd_discover)

    sp = sub.add_parser("scan", help="Read every mapped board and write the India feed")
    sp.add_argument("--boards", default="feed/boards.json")
    sp.add_argument("--out", default="feed")
    sp.add_argument("--workers", type=int, default=16)
    sp.add_argument("--detail-cap", type=int, default=400, help="Max SmartRecruiters detail requests per scan")
    sp.add_argument("--no-remote-boards", action="store_true", help="Company boards only")
    sp.set_defaults(fn=cmd_scan)

    sp = sub.add_parser("filter-feed", help="Apply your filters to the India feed")
    sp.add_argument("--feed", default="https://raw.githubusercontent.com/VishStack01/careeros/feed/feed/india.jsonl.gz")
    sp.add_argument("--settings-json", help="The dashboard's settings/profile document (JSON)")
    sp.add_argument("--settings", default="config/settings.toml")
    sp.add_argument("--known", help="Folder or file of roles already on the dashboard")
    sp.add_argument("--out", default="new")
    sp.add_argument("--max-skips", type=int, default=60)
    sp.add_argument("--max-kept", type=int, default=400)
    sp.set_defaults(fn=cmd_filter_feed)

    sp = sub.add_parser("platforms", help="Job platforms for the agent to visit this run")
    sp.add_argument("--file", help="Registry TOML (default: config/platforms.toml)")
    sp.add_argument("--run", type=int, help="Run number for the rotation (default: from the clock)")
    sp.add_argument("--all", action="store_true")
    sp.add_argument("--json", action="store_true")
    sp.set_defaults(fn=cmd_platforms)

    sp = sub.add_parser("serve")
    sp.add_argument("--port", type=int, default=8765)
    sp.add_argument("--root", default="dashboard")
    sp.set_defaults(fn=cmd_serve)

    a = p.parse_args(argv)
    a.fn(a)


if __name__ == "__main__":
    main()
