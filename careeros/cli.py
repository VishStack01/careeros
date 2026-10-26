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
  careeros eval-check EVAL.json [--job-id ID] [--jd JD.txt] [--md REPORT.md] [--save]
                                        check a scored evaluation (1-5, apply line 4.0) and write its report
  careeros liveness URL [URL ...]       is a posting still open?
  careeros archive-jd URL [--job-id ID] save the posting's full text verbatim
  careeros render resume.json --out resume.pdf [--profile P.json]
                                        ATS-safe PDF from a checked resume (then checks the PDF)
  careeros pdf-check resume.pdf --resume resume.json
  careeros keywords --jd jd.txt --resume resume.json
                                        which posting terms the resume uses (never an "ATS score")
  careeros writing-check note.txt       clichés and filler in a cover note or message
  careeros stats | calibrate | gaps     the funnel, score calibration and the skills gap
  careeros followups                    follow-ups due (day 7 and 14 after applying, thank-yous)
  careeros classify-reply email.txt     confirmation, rejection, assessment, interview or offer?
  careeros warm-intros --connections Connections.csv
                                        people you know at the companies you're applying to
  careeros salary-gap --job-id ID       pay side by side: advertised, floor, ask, what you said, the offer
  careeros funded [--add "A,B"]         companies that just raised money (review first)
  careeros doctor [--online]            is this install ready, and is your private data private?
  careeros pause | resume               kill switch for all submissions
  careeros serve [--port 8765]          open the dashboard locally

India feed (runs on GitHub Actions; see .github/workflows/scan.yml):
  careeros discover                     find each company's public job board
  careeros radar                        companies hiring on Indeed/Naukri (via JobSpy) -> their own boards
  careeros scan                         read every mapped board, write feed/india.jsonl.gz
  careeros filter-feed --feed URL --settings-json S.json --known DIR --out DIR
                                        apply your filters to the feed (agent use)
  careeros platforms [--run N] [--json] job platforms for the agent to visit this run
  careeros site --feed feed --out site  build the public job board (GitHub Pages)
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
    if a.submit and job:
        from .evaluation import apply_gate
        ok, why = apply_gate(job, chosen_by_user=True)
        if not ok and not a.below_line:
            sys.exit(f"Not submitting: {why} (or pass --below-line).")
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
        from . import followups
        patch = {"stage": "applied", "appliedAt": stamp, "appliedVia": "careeros",
                 "timeline": cur.get("timeline", []) + [{"at": stamp, "event": "Applied; confirmation captured"}]}
        patch["followUps"] = followups.seed(dict(cur, **patch))
        store.update("jobs", a.job_id, patch)


def cmd_pause(a):
    Store(a.db).set_flag("paused", True)
    print("Paused. No application will be submitted until you run `careeros resume`.")


def cmd_resume(a):
    Store(a.db).set_flag("paused", False)
    print("Resumed.")


def cmd_discover(a):
    from . import discover
    discover.run(a.companies, a.cache, refresh_days=a.refresh_days, workers=a.workers, limit=a.limit, max_minutes=a.max_minutes,
                 extra=a.extra or [])


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


def cmd_site(a):
    from . import site
    site.build(a.feed, a.out, demo=a.demo, base_url=a.base_url)


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
    sp.add_argument("--below-line", action="store_true", help="Submit even though the role scored under 4.0")
    sp.set_defaults(fn=cmd_apply)

    sub.add_parser("pause").set_defaults(fn=cmd_pause)
    sub.add_parser("resume").set_defaults(fn=cmd_resume)

    sp = sub.add_parser("discover", help="Find public job boards for the company list")
    sp.add_argument("--companies", default="config/companies/companies.csv")
    sp.add_argument("--cache", default="feed/boards.json")
    sp.add_argument("--refresh-days", type=int, default=14)
    sp.add_argument("--workers", type=int, default=32)
    sp.add_argument("--limit", type=int)
    sp.add_argument("--max-minutes", type=float, help="Stop starting new companies after this long")
    sp.add_argument("--extra", action="append", help="Another company list to include (e.g. feed/radar-companies.csv)")
    sp.set_defaults(fn=cmd_discover)

    sp = sub.add_parser("radar", help="Learn which companies are hiring from Indeed/Naukri (via JobSpy), then map their own boards")
    sp.add_argument("--config", default="config/radar.toml")
    sp.add_argument("--boards", default="feed/boards.json")
    sp.add_argument("--out", default="feed/radar-companies.csv")
    sp.set_defaults(fn=cmd_radar)

    sp = sub.add_parser("referrals", help="Who to ask for a referral at a company, and drafted notes you send")
    sp.add_argument("--company", required=True)
    sp.add_argument("--title", required=True)
    sp.add_argument("--url", help="The job posting, quoted in the referral ask")
    sp.add_argument("--connections", help="LinkedIn's Connections.csv export")
    sp.add_argument("--people", help="JSON list of public profiles found by web search: {name, headline, url, location, degree}")
    sp.add_argument("--applicant", help="Your applicant profile JSON (name, college, city, current role)")
    sp.add_argument("--json", action="store_true")
    sp.set_defaults(fn=cmd_referrals)

    sp = sub.add_parser("payers", help="Early-career pay by company from real offers (leetcode-compensation, MIT)")
    sp.add_argument("--out", default="config/pay/offers-pay.csv")
    sp.add_argument("--source", help="A local copy of final_data.json instead of downloading it")
    sp.add_argument("--max-yoe", type=float, default=1.5)
    sp.add_argument("--min-offers", type=int, default=2)
    sp.set_defaults(fn=cmd_payers)

    sp = sub.add_parser("ats-check", help="How an applicant-tracking system reads your resume PDF, with fixes")
    sp.add_argument("pdf")
    sp.add_argument("--applicant", help="profile/applicant JSON (name, email, experience)")
    sp.add_argument("--terms", help="market.json from `careeros market --json`, to check keyword coverage")
    sp.add_argument("--json", action="store_true")
    sp.set_defaults(fn=cmd_ats)

    sp = sub.add_parser("market", help="What the roles that pay your floor ask for, against your resume")
    sp.add_argument("--feed", default="feed/india.jsonl.gz")
    sp.add_argument("--settings", help="Dashboard settings JSON (targetRoles, titleExclude, salaryFloorLpa, maxRequiredYears)")
    sp.add_argument("--resume", help="Your resume PDF or text file")
    sp.add_argument("--top", type=int, default=20)
    sp.add_argument("--json", action="store_true")
    sp.set_defaults(fn=cmd_market)

    sp = sub.add_parser("deep", help="List thousands of company boards from the open ATS inventory for discover to check")
    sp.add_argument("--boards", default="feed/boards.json")
    sp.add_argument("--out", default="feed/deep-companies.csv")
    sp.add_argument("--ats", action="append", help="Only this hiring system (repeatable)")
    sp.set_defaults(fn=cmd_deep)

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

    sp = sub.add_parser("site", help="Build the public job board from the feed")
    sp.add_argument("--feed", default="feed")
    sp.add_argument("--out", default="site")
    sp.add_argument("--demo", default="dashboard/index.html", help="Dashboard demo page to include at /demo/")
    sp.add_argument("--base-url", default="", help="Public URL of the board, for API links and RSS")
    sp.set_defaults(fn=cmd_site)

    sp = sub.add_parser("serve")
    sp.add_argument("--port", type=int, default=8765)
    sp.add_argument("--root", default="dashboard")
    sp.set_defaults(fn=cmd_serve)

    sp = sub.add_parser("liveness", help="Is a posting still open? (hiring-system API first, then the page)")
    sp.add_argument("urls", nargs="+")
    sp.add_argument("--json", action="store_true")
    sp.set_defaults(fn=cmd_liveness)

    sp = sub.add_parser("eval-check", help="Check a scored evaluation (1-5) and write its report")
    sp.add_argument("evaluation", help="Evaluation JSON written by the evaluate skill")
    sp.add_argument("--job", help="The job's JSON document (for the report header and posting checks)")
    sp.add_argument("--job-id", help="Or: the role's id in the local database")
    sp.add_argument("--jd", help="The posting's text: quotes are checked against it and it is archived in the report")
    sp.add_argument("--brain", default="brain/brain.json", help="Claim ids are checked against it when the file exists")
    sp.add_argument("--md", help="Write the report here")
    sp.add_argument("--save", action="store_true", help="Store the evaluation on the role (needs --job-id)")
    sp.add_argument("--patch-out", help="Write the job fields to set (evaluation, score, decision, fit, evidence, gaps, archived posting) as JSON")
    sp.set_defaults(fn=cmd_eval_check)

    sp = sub.add_parser("render", help="Render a checked resume.json or a cover note to an ATS-safe PDF")
    sp.add_argument("resume", nargs="?", help="resume.json (already passed claims-check)")
    sp.add_argument("--cover", help="A cover note (text file) to render instead")
    sp.add_argument("--company", default="")
    sp.add_argument("--brain", default="brain/brain.json")
    sp.add_argument("--profile", help="Applicant details JSON (fullName, email, phone, city, links)")
    sp.add_argument("--out", required=True, help="PDF path")
    sp.add_argument("--html", help="Also write the HTML here")
    sp.set_defaults(fn=cmd_render)

    sp = sub.add_parser("pdf-check", help="Check a resume PDF says what the checked resume.json says, and nothing more")
    sp.add_argument("pdf")
    sp.add_argument("--resume", required=True)
    sp.add_argument("--brain", default="brain/brain.json")
    sp.add_argument("--profile")
    sp.set_defaults(fn=cmd_pdf_check)

    sp = sub.add_parser("keywords", help="Which of the posting's terms the resume uses (never an 'ATS score')")
    sp.add_argument("--jd", required=True, help="The posting's text")
    sp.add_argument("--resume", required=True, help="resume.json, or a PDF")
    sp.add_argument("--terms", help="Comma-separated terms (default: found in the posting)")
    sp.add_argument("--json", action="store_true")
    sp.set_defaults(fn=cmd_keywords)

    sp = sub.add_parser("writing-check", help="Flag clichés and filler in a cover note, answer or message")
    sp.add_argument("file")
    sp.add_argument("--brain", default="brain/brain.json", help="Your banned words come from its voice profile")
    sp.set_defaults(fn=cmd_writing_check)

    sp = sub.add_parser("archive-jd", help="Save a posting's full text verbatim before applying")
    sp.add_argument("url")
    sp.add_argument("--company", default="")
    sp.add_argument("--job-id", help="Also store the text on this role in the local database")
    sp.add_argument("--out", default="jds")
    sp.set_defaults(fn=cmd_archive_jd)

    for name, fn, hlp in (("stats", "cmd_stats", "The funnel, response rates and speed"),
                          ("calibrate", "cmd_calibrate", "Do higher scores get more replies?"),
                          ("gaps", "cmd_gaps", "Skills your kept roles ask for that the brain can't prove yet"),
                          ("followups", "cmd_followups", "Follow-ups due now (day 7 and 14 after applying, thank-yous)")):
        sp = sub.add_parser(name, help=hlp)
        sp.add_argument("--jobs", help="A folder of job JSON documents (default: the local database)")
        sp.add_argument("--json", action="store_true")
        if name == "stats":
            sp.add_argument("--days", type=int, default=30)
        if name == "gaps":
            sp.add_argument("--brain", default="brain/brain.json")
        sp.set_defaults(fn=globals()[fn])

    sp = sub.add_parser("classify-reply", help="Sort an email from a company: confirmation, rejection, interview...")
    sp.add_argument("file", help="The email as text (subject on the first line)")
    sp.set_defaults(fn=cmd_classify_reply)

    sp = sub.add_parser("warm-intros", help="People you know at the companies in your pipeline (LinkedIn's Connections.csv)")
    sp.add_argument("--connections", required=True)
    sp.add_argument("--company", help="One company instead of the whole pipeline")
    sp.add_argument("--jobs")
    sp.add_argument("--json", action="store_true")
    sp.set_defaults(fn=cmd_warm_intros)

    sp = sub.add_parser("doctor", help="Is this install ready, and is your private data private?")
    sp.add_argument("--online", action="store_true", help="Also check the network")
    sp.set_defaults(fn=lambda a: sys.exit(__import__("careeros.doctor", fromlist=["run"]).run(Path.cwd(), a.db, a.online)))

    sp = sub.add_parser("salary-gap", help="Pay side by side: advertised, your floor and ask, what you said, the offer")
    sp.add_argument("--job-id")
    sp.add_argument("--jobs")
    sp.add_argument("--advertised")
    sp.add_argument("--ask")
    sp.add_argument("--floor")
    sp.add_argument("--offer")
    sp.add_argument("--json", action="store_true")
    sp.set_defaults(fn=cmd_salary_gap)

    sp = sub.add_parser("funded", help="Companies that just raised money (review first, then --add)")
    sp.add_argument("--days", type=int, default=30)
    sp.add_argument("--feeds", help="Comma-separated RSS feed URLs or files (default: Inc42, Entrackr, TechCrunch India)")
    sp.add_argument("--companies", default="config/companies/companies.csv")
    sp.add_argument("--add", help="Comma-separated company names from the list to add to companies.csv")
    sp.add_argument("--json", action="store_true")
    sp.set_defaults(fn=cmd_funded)

    sp = sub.add_parser("cloud", help="The multi-user service: migrate, serve, worker, ingest")
    sp.add_argument("action", choices=["migrate", "serve", "worker", "ingest", "match-all", "check"])
    sp.add_argument("--host", default="127.0.0.1")
    sp.add_argument("--port", type=int, default=8000)
    sp.add_argument("--force", action="store_true", help="ingest: accept a feed even if it shrank sharply")
    sp.set_defaults(fn=cmd_cloud)

    a = p.parse_args(argv)
    a.fn(a)


def cmd_eval_check(a) -> None:
    from . import evaluation
    ev = json.loads(Path(a.evaluation).read_text(encoding="utf-8"))
    store = Store(a.db) if a.job_id else None
    job = json.loads(Path(a.job).read_text(encoding="utf-8")) if a.job else ((store.get("jobs", a.job_id) or {}).get("data", {}) if store else {})
    job = job.get("data", job)
    jd = Path(a.jd).read_text(encoding="utf-8") if a.jd else (job.get("description") or None)
    br = brain.load(a.brain) if a.brain and Path(a.brain).exists() else None
    errors, warnings = evaluation.validate(ev, jd=jd, brain=br)
    for e in errors:
        print(f"ERROR  {e}")
    for w in warnings:
        print(f"WARN   {w}")
    if errors:
        sys.exit(f"\n{len(errors)} problem(s): fix them and run eval-check again.")
    norm = evaluation.normalize(ev)
    v = norm["verdict"]
    print(f"Score {norm['score']:.1f}/5: {v['label']} Confidence: {norm['confidence']}.")
    if a.md:
        Path(a.md).parent.mkdir(parents=True, exist_ok=True)
        Path(a.md).write_text(evaluation.report_md(norm, job, jd), encoding="utf-8")
        print(f"Report: {a.md}")
    patch = evaluation.job_patch(norm, ev.get("decision"))
    if a.jd:
        patch.update(jd=jd, jdArchivedAt=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"))
    if a.patch_out:
        Path(a.patch_out).write_text(json.dumps(patch, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"Job fields: {a.patch_out}")
    if a.save:
        if not (store and store.get("jobs", a.job_id)):
            sys.exit("--save needs --job-id of a role in the local database.")
        store.update("jobs", a.job_id, patch)
        print(f"Saved on {a.job_id}.")


def _json_or_none(path):
    return json.loads(Path(path).read_text(encoding="utf-8")) if path else None


def cmd_render(a) -> None:
    from . import render
    br = brain.load(a.brain)
    prof = _json_or_none(a.profile)
    if a.cover:
        page = render.cover_html(Path(a.cover).read_text(encoding="utf-8"), br, prof, a.company)
    elif a.resume:
        res = json.loads(Path(a.resume).read_text(encoding="utf-8"))
        rep = claims.check(res, br)
        if not rep.ok:
            for b in rep.blocking:
                print(f"BLOCK  {b}")
            sys.exit("Not rendering: resume.json fails the claims check.")
        page = render.resume_html(res, br, prof)
    else:
        sys.exit("Give a resume.json or --cover.")
    if a.html:
        Path(a.html).write_text(page, encoding="utf-8")
    out = render.to_pdf(page, a.out)
    print(f"Wrote {out}")
    if a.resume and not a.cover:
        rep = claims.check_pdf(render.pdf_text(out), res, br, prof)
        for b in rep.blocking:
            print(f"BLOCK  {b}")
        print("PDF check: " + ("OK, the PDF says what resume.json says." if rep.ok else "blocked."))
        sys.exit(0 if rep.ok else 1)


def cmd_pdf_check(a) -> None:
    from . import render
    res = json.loads(Path(a.resume).read_text(encoding="utf-8"))
    rep = claims.check_pdf(render.pdf_text(a.pdf), res, brain.load(a.brain), _json_or_none(a.profile))
    for b in rep.blocking:
        print(f"BLOCK  {b}")
    for w in rep.warnings:
        print(f"WARN   {w}")
    print("OK to send." if rep.ok else "Blocked: fix the lines above.")
    sys.exit(0 if rep.ok else 1)


def cmd_keywords(a) -> None:
    from . import keywords
    jd = Path(a.jd).read_text(encoding="utf-8")
    if a.resume.lower().endswith(".pdf"):
        from . import render
        res = render.pdf_text(a.resume)
    else:
        res = json.loads(Path(a.resume).read_text(encoding="utf-8"))
    terms = [t for t in (a.terms or "").split(",") if t.strip()] or keywords.extract(jd)
    cov = keywords.coverage(terms, res)
    if a.json:
        print(json.dumps(cov, indent=2))
        return
    print(cov["summary"])
    for k, label in (("present", "In a bullet or summary"), ("thin", "Only in the skills list"), ("missing", "Missing (add only with a brain claim)")):
        if cov[k]:
            print(f"  {label}: {', '.join(cov[k])}")


def cmd_writing_check(a) -> None:
    from . import writing
    text = Path(a.file).read_text(encoding="utf-8")
    banned = (brain.load(a.brain).get("voice") or {}).get("banned_words") if a.brain and Path(a.brain).exists() else None
    found = writing.check(text, banned)
    for f in found:
        print(f"{'line ' + str(f.line) if f.line else 'note':>8}  \"{f.phrase}\": {f.why}. Instead: {f.instead}.")
    if not writing.specific(text):
        print("    note  No number or named piece of work: add one real proof point.")
    print(f"{len(found)} thing(s) to rewrite." if found else "Reads cleanly.")


def cmd_archive_jd(a) -> None:
    from . import jd
    got = jd.fetch(a.url)
    path = jd.save(got, a.out, a.company, a.job_id or "")
    print(f"Archived {len(got['text']):,} characters via {got['via']}: {path}")
    if a.job_id:
        store = Store(a.db)
        if store.get("jobs", a.job_id):
            store.update("jobs", a.job_id, {"jd": got["text"], "jdArchivedAt": iso(datetime.now(timezone.utc)), "jdPath": str(path)})
            print(f"Stored on {a.job_id}.")


def _jobs(a) -> list[dict]:
    if getattr(a, "jobs", None):
        from .feed import _known_docs
        return [dict(d, id=i) for i, d in _known_docs(a.jobs)]
    return [dict(d["data"], id=d["id"]) for d in Store(a.db).list("jobs")]


def cmd_stats(a) -> None:
    from . import analytics
    st = analytics.stats(_jobs(a), days=a.days)
    if a.json:
        print(json.dumps(st, indent=2))
        return
    f = st["funnel"]
    print(f"Last {st['days']} days: {st['roles']} roles")
    print("  " + " -> ".join(f"{k} {f[k]}" for k in ("found", "applied", "screen", "interview", "offer")))
    print(f"  Replies: {st['responseRate']}" + ("  (small sample)" if st["smallSample"] else "") + f", rejections {st['rejected']}")
    if st["medianDaysToResponse"] is not None:
        print(f"  Median wait for a reply: {st['medianDaysToResponse']} days")
    if st["medianHoursPostToApply"] is not None:
        print(f"  Median time from posting to applying: {st['medianHoursPostToApply']} hours")
    for k, label in (("byRegion", "By region"), ("byArchetype", "By role family"), ("bySource", "By source")):
        rows = [f"{name} {v['rate']}{'*' if v['small'] else ''}" for name, v in list(st[k].items())[:6]]
        if rows:
            print(f"  {label}: " + "; ".join(rows))
    if st["skipsByGate"]:
        print("  Skipped most by: " + ", ".join(f"{g} {n}" for g, n in st["skipsByGate"].items()))
    print("  * fewer than 10 applications")


def cmd_calibrate(a) -> None:
    from . import analytics
    c = analytics.calibrate(_jobs(a))
    if a.json:
        print(json.dumps(c, indent=2))
        return
    print(f"{'Score':<10} {'Applied':>8} {'Replies':>12} {'Interviews':>11}")
    for r in c["bands"]:
        print(f"{r['band']:<10} {r['applied']:>8} {r['responseRate']:>12} {r['interviews']:>11}{'  small sample' if r['small'] and r['applied'] else ''}")
    if c["unscored"]:
        print(f"{c['unscored']} application(s) weren't scored.")
    if c["note"]:
        print(c["note"])


def cmd_gaps(a) -> None:
    from . import analytics
    br = brain.load(a.brain) if a.brain and Path(a.brain).exists() else None
    rows = analytics.gaps(_jobs(a), br)
    if a.json:
        print(json.dumps(rows, indent=2))
        return
    if not rows:
        print("No gaps found in the roles you kept.")
    for r in rows:
        print(f"{r['roles']:>3} roles  {r['skill']}" + (f"  (partly there in {r['partly']})" if r["partly"] else "") + f"  e.g. {'; '.join(r['examples'])}")


def cmd_followups(a) -> None:
    from . import followups
    items = followups.due(_jobs(a))
    if a.json:
        print(json.dumps([{"job": j.get("id"), "company": j.get("company"), **f} for j, f in items], indent=2))
        return
    for j, f in items:
        print(f"{f.get('due', '')[:10]}  {f.get('label', 'Follow-up'):<24} {j.get('title', '')} at {j.get('company', '')}")
    print(f"{len(items)} follow-up(s) due." if items else "Nothing due.")


def cmd_classify_reply(a) -> None:
    from . import replies
    text = Path(a.file).read_text(encoding="utf-8")
    subject, _, body = text.partition("\n")
    print(json.dumps(replies.classify(subject, body), indent=2, ensure_ascii=False))


def cmd_warm_intros(a) -> None:
    from . import connections
    rows = connections.parse(Path(a.connections).read_text(encoding="utf-8-sig"))
    companies = [a.company] if a.company else sorted({j.get("company", "") for j in _jobs(a) if j.get("stage") not in ("skipped", "rejected", "withdrawn")})
    out = {c: connections.matches(c, rows) for c in companies if c}
    out = {c: m for c, m in out.items() if m}
    if a.json:
        print(json.dumps(out, indent=2, ensure_ascii=False))
        return
    print(f"{len(rows)} connections read.")
    for c, ms in out.items():
        print(f"\n{c}")
        for m in ms:
            print(f"  [{m['tier']:<6}] {m['name']}, {m['position'] or 'no title'} at {m['company']}")
    if not out:
        print("Nobody you know at these companies yet.")


def cmd_salary_gap(a) -> None:
    from . import salary_gap
    if a.job_id:
        jobs = {j.get("id"): j for j in _jobs(a)}
        if a.job_id not in jobs:
            sys.exit(f"No role with id {a.job_id}")
        s = Settings.load("config/settings.toml") if Path("config/settings.toml").exists() else Settings()
        res = salary_gap.for_job(jobs[a.job_id], {"salaryFloorLpa": s.salary_floor_lpa}, None)
        if a.ask or a.offer:
            res = salary_gap.compare(a.advertised or jobs[a.job_id].get("salary"), a.ask, a.floor or s.salary_floor_lpa, a.offer or (jobs[a.job_id].get("offer") or {}).get("ctc"),
                                     jobs[a.job_id].get("salaryStated"))
    else:
        res = salary_gap.compare(a.advertised, a.ask, a.floor, a.offer)
    if a.json:
        print(json.dumps(res, indent=2, ensure_ascii=False))
        return
    for r in res["rows"]:
        print(f"  {r['what']:<20} {r['lpa']}")
    for f in res["findings"]:
        print(f"- {f}")
    print("Facts, not advice: the `coach` skill turns these into a negotiation brief.")


def cmd_funded(a) -> None:
    from . import funded
    if a.feeds:
        items = []
        for src in a.feeds.split(","):
            src = src.strip()
            if src.startswith("http"):
                got, errs = funded.fetch([src])
                items += got
                for e in errs:
                    print(f"WARN   {e}", file=sys.stderr)
            elif src:
                items += funded.parse_feed(Path(src).read_bytes())
    else:
        items, errs = funded.fetch()
        for e in errs:
            print(f"WARN   {e}", file=sys.stderr)
    found = funded.candidates(items, funded.known_keys(a.companies), days=a.days)
    if a.add:
        added = funded.add([n for n in a.add.split(",") if n.strip()], found, a.companies)
        print(f"Added {len(added)} to {a.companies}: {', '.join(added) or 'none (already listed?)'}. Run `careeros discover` to find their job boards.")
        return
    if a.json:
        print(json.dumps(found, indent=2, ensure_ascii=False))
        return
    new = [c for c in found if not c["tracked"]]
    for c in new:
        print(f"{c['date']}  {c['company']:<28} {c['amount']:<12} {c['round']:<10} {c['source']}")
    print(f"\n{len(new)} new, {len(found) - len(new)} already tracked. Add the ones you want: careeros funded --add \"Name One,Name Two\"")


def cmd_radar(a) -> None:
    from . import discover
    from .sources import radar
    cfg = radar.load_config(a.config)
    rows = radar.search(cfg)
    found = radar.harvest(rows)
    cache_path = Path(a.boards)
    cache = json.loads(cache_path.read_text(encoding="utf-8")) if cache_path.exists() else {"companies": {}}
    res = radar.merge(found, cache, a.out, discover.probe, discover.accept)
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(json.dumps(cache, indent=1, ensure_ascii=False), encoding="utf-8")
    print(f"Radar: {len(rows)} listings read, {len(found['boards'])} employer boards and {len(found['companies'])} companies seen; "
          f"{res['boardsAdded']} boards added to the scan, {res['companiesAdded']} companies queued for discovery.")


def cmd_deep(a) -> None:
    from . import deep
    cache_path = Path(a.boards)
    cache = json.loads(cache_path.read_text(encoding="utf-8")) if cache_path.exists() else {"companies": {}}
    rows = deep.fetch(a.ats or deep.ATS)
    todo = deep.build(rows, cache)
    if not rows and Path(a.out).exists():
        print("Deep sweep: inventory unavailable; keeping the last list.")
        return
    deep.write(todo, a.out)
    st = deep.stats(cache)
    print(f"Deep sweep: {len(rows)} boards in the open inventory, {len(todo)} on the list for discover; "
          f"{st['checked']} checked so far, {st['mapped']} kept for listing developer roles in India or open to it.")


def cmd_referrals(a) -> None:
    from . import connections, referrals
    rows = connections.parse(Path(a.connections).read_text(encoding="utf-8", errors="replace")) if a.connections else []
    people = json.loads(Path(a.people).read_text(encoding="utf-8")) if a.people else []
    appl = json.loads(Path(a.applicant).read_text(encoding="utf-8")) if a.applicant else {}
    appl = appl.get("data", appl) if isinstance(appl, dict) else {}
    out = referrals.plan(a.company, a.title, appl, rows, people, a.url or "")
    if a.json:
        print(json.dumps(out, indent=2, ensure_ascii=False))
        return
    print(f"Referral plan: {a.title} at {a.company}\n")
    for i, p in enumerate(out["people"], 1):
        print(f"{i}. {p['name']} ({p['score']}) {p['headline']}\n   {'; '.join(p['why'])}\n   {p['url']}")
    if not out["people"]:
        print("Nobody found yet. Open these searches in your browser (signed in to LinkedIn):")
    for l in out["searchLinks"]:
        print(f"  - {l['label']}: {l['url']}")
    print(f"\nConnection note ({len(out['drafts']['connectionNote'])} characters):\n{out['drafts']['connectionNote']}")
    print(f"\nReferral ask:\n{out['drafts']['referralAsk']}")


def cmd_payers(a) -> None:
    from . import paydata
    from .sources import http
    src = Path(a.source) if a.source else None
    records = json.loads(src.read_text(encoding="utf-8")) if src else http.get_json(paydata.OFFERS_URL, timeout=60)
    rows = paydata.offer_bands(records, max_yoe=a.max_yoe, min_n=a.min_offers)
    paydata.write_offers(rows, Path(a.out))
    top = ", ".join(f"{r['company']} {r['low_lpa']:g}" for r in rows[:8])
    print(f"Pay data: {len(records)} offers read; {len(rows)} companies with {a.min_offers}+ offers at up to {a.max_yoe:g} years "
          f"({sum(r['low_lpa'] >= 15 for r in rows)} with a median base of 15 LPA or more). Top: {top}")


def cmd_ats(a) -> None:
    from . import ats
    rep = ats.check_file(a.pdf, profile=_load_json(a.applicant), terms=_terms(a.terms))
    if a.json:
        print(json.dumps(rep, indent=2, ensure_ascii=False))
        return
    print(f"ATS readiness: {rep['score']}/100 ({rep['pages']} page{'s' if rep['pages'] != 1 else ''}, {rep['words']} words)\n")
    for c in rep["checks"]:
        print(f"{'PASS' if c['ok'] else 'FIX '}  {c['title']}" + ("" if c["ok"] else f"\n      {c['fix']}"))


def cmd_market(a) -> None:
    import gzip
    from . import market
    with gzip.open(a.feed, "rt", encoding="utf-8") as f:
        records = [json.loads(l) for l in f if l.strip()]
    settings = _load_json(a.settings)
    resume = market.resume_text(a.resume) if a.resume else ""
    out = market.analyze(records, settings, resume, top=a.top)
    if a.json:
        print(json.dumps(out, indent=2, ensure_ascii=False))
        return
    fn = out["funnel"]
    print("Market for your filters: " + " -> ".join(f"{k} {v}" for k, v in fn.items()))
    print("\nSkills most asked for in roles paying your floor (share of those roles):")
    for s in out["skills"]:
        print(f"  {s['share']:>4.0%}  {s['skill']:<22} {'on your resume' if s['onResume'] else 'MISSING from your resume'}")
    print("\nCompanies with the most of these roles: " + ", ".join(f"{c['company']} ({c['roles']})" for c in out["companies"][:12]))


def _load_json(path):
    if not path:
        return {}
    d = json.loads(Path(path).read_text(encoding="utf-8"))
    return d.get("data", d) if isinstance(d, dict) else {}


def _terms(path):
    if not path:
        return []
    d = json.loads(Path(path).read_text(encoding="utf-8"))
    return [s["skill"] if isinstance(s, dict) else str(s) for s in (d.get("skills", d) if isinstance(d, dict) else d)]


def cmd_liveness(a) -> None:
    from . import liveness
    results = []
    for u in a.urls:
        r = liveness.check(u)
        results.append(dict(r.to_dict(), url=u))
        if not a.json:
            mark = {"open": "OPEN  ", "closed": "CLOSED", "uncertain": "??    "}[r.status]
            print(f"{mark} {u}\n       {r.reason}" + (f"\n       \"{r.evidence}\"" if r.evidence else ""))
    if a.json:
        print(json.dumps(results, indent=2))


def cmd_cloud(a) -> None:
    try:
        from .cloud.config import Config
        from .cloud.db import Database
    except ImportError as e:  # pragma: no cover
        raise SystemExit(f"The cloud service needs its extras: pip install \"careeros[cloud]\" ({e})")
    cfg = Config.from_env()
    if a.action == "check":
        problems = cfg.check()
        print("\n".join(problems) if problems else f"Configuration looks safe for {cfg.app_env}.")
        raise SystemExit(1 if problems else 0)
    if a.action == "serve":
        import uvicorn

        from .cloud.app import create_app
        uvicorn.run(create_app(cfg), host=a.host, port=a.port, proxy_headers=cfg.trust_proxy, forwarded_allow_ips="*" if cfg.trust_proxy else None)
        return
    if a.action == "worker":
        from .cloud.worker import main as worker_main
        worker_main(cfg)
        return
    db = Database(cfg.database_url, cfg.db_pool_min, cfg.db_pool_max)
    try:
        if a.action == "migrate":
            applied = db.migrate()
            print(f"{len(applied)} migration(s) applied." if applied else "Database is up to date.")
        elif a.action == "ingest":
            from .cloud.ingest import ingest
            print(ingest(db, cfg.feed_url, force=a.force))
        elif a.action == "match-all":
            from .cloud.worker import Worker
            print(f"queued {Worker(cfg, db).queue_matches()} match task(s)")
    finally:
        db.close()


if __name__ == "__main__":
    main()
