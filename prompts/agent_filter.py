# CareerOS feed filter for sandboxed agents (standard library only).
# Same decisions as `careeros filter-feed`, using the facts the scan already
# extracted. The scheduled prompt carries this script so the agent writes it
# itself instead of running downloaded code.
# Usage: python3 agent_filter.py FEED.jsonl.gz SETTINGS.json KNOWN_DIR OUT_DIR MAX_KEPT [MAX_SKIPS=40] [SUMMARY.json]
# Writes OUT_DIR/kept/*.json, OUT_DIR/skipped/*.json and OUT_DIR/index.json (kept, skipped, gone, expired).
import glob, gzip, hashlib, json, os, re, sys
from datetime import datetime, timezone

feed_p, set_p, known_p, out_p, max_kept = sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4], int(sys.argv[5])
max_skips = int(sys.argv[6]) if len(sys.argv) > 6 else 40
summary = json.load(open(sys.argv[7])) if len(sys.argv) > 7 and os.path.exists(sys.argv[7]) else None
S = json.load(open(set_p)); S = S.get("data", S)
AI = ["ai", "a.i.", "artificial intelligence", "genai", "gen ai", "generative", "llm", "agent", "agentic", "machine learning", "ml",
      "mlops", "applied scientist", "nlp", "computer vision", "prompt", "automation", "forward deployed", "data scientist",
      "ai product", "conversational", "rag"]
roles = [r.lower() for r in S.get("targetRoles") or []] + AI
excl = [r.lower() for r in S.get("titleExclude") or []]
block = [b.lower() for b in S.get("companyBlocklist") or []]
deal = [d.strip() for d in re.split(r"[,\n]", str(S.get("dealbreakers") or "")) if d.strip()]
kw = lambda ws: re.compile("|".join(r"(?<![a-z0-9])" + re.escape(w) + r"(?:s|es)?(?![a-z0-9])" for w in ws) or r"(?!x)x", re.I)
ROLE, EXCL = kw(roles), kw(excl)
max_y = float(S.get("maxRequiredYears", 1) if S.get("maxRequiredYears") is not None else 1)
days = int(S.get("maxPostingAgeDays") or 25)
floor = S.get("salaryFloorLpa"); floor = float(floor) if floor not in (None, "", 0) else None
locs = " ".join(S.get("locations") or []).lower()
south = "any" if ("south india (any" in locs or not locs) else ("remote" if "south india (remote" in locs else "never")
rest = "any" if "rest of india (any" in locs else ("remote" if ("rest of india (remote" in locs or not locs) else "never")
abroad = "remote" if ("worldwide" in locs or "global" in locs or not locs) else "never"
now = datetime.now(timezone.utc)
iso = lambda d: d.strftime("%Y-%m-%dT%H:%M:%SZ")
NOISE = re.compile(r"\b(private|pvt|limited|ltd|llp|inc|incorporated|corp|corporation|co|company|technologies|technology|labs?|solutions|software|systems|ai|india|the)\b")
norm = lambda s: re.sub(r"\s+", " ", re.sub(r"[^a-z0-9+#.]+", " ", (s or "").lower())).strip()
def fp(c, t):
    ck = re.sub(r"\s+", " ", NOISE.sub(" ", norm(c))).strip() or norm(c)
    return hashlib.sha1((ck + "|" + norm(re.sub(r"\([^)]*\)", " ", t or ""))).encode()).hexdigest()[:16]
curl = lambda u: re.sub(r"[?#].*$", "", (u or "").strip()).rstrip("/").lower()

ids, urls, fps, known = set(), set(), set(), []
for f in glob.glob(os.path.join(known_p, "**", "*.json"), recursive=True):
    try: d = json.load(open(f)); d = d.get("data", d) if "data" in d and isinstance(d.get("data"), dict) else d
    except Exception: continue
    i = os.path.basename(f)[:-5]; known.append((i, d))
    ids.add(i); urls.add(curl(d.get("url"))); fps.add(fp(d.get("company"), d.get("title")))

def decide(r):
    f, t = r.get("facts") or {}, r["title"]
    c = [("Company", not any(b in r["company"].lower() for b in block), r["company"], "")]  # (gate, passed, value, quote)
    c.append(("Role", bool(ROLE.search(t)) and not EXCL.search(t), "Target role" if ROLE.search(t) and not EXCL.search(t) else "The title isn't one of your target roles.", t))
    c.append(("Seniority", not (f.get("senior") and max_y < 3), "Senior title" if f.get("senior") else "Not stated in title", t))
    e = f.get("expMin")
    ev = ("Fresher welcome" if f.get("fresherOk") else "Not stated") if e is None else (f"{e:g}+ years" if e else "Fresher (0 years)")
    eok = not (e is not None and e > max_y) and not (e is None and f.get("fresherOk") is False and max_y < 1)
    c.append(("Experience", eok, ev if eok else f"Asks for {ev}; your limit is {max_y:g} year(s).", f.get("expQuote") or ""))
    try:
        pd = datetime.fromisoformat((r.get("postedAt") or "").replace("Z", "+00:00")); pd = pd if pd.tzinfo else pd.replace(tzinfo=timezone.utc)
        age = (now - pd).total_seconds() / 86400
    except ValueError:
        age = None
    lab = "Posting date not shown" if age is None else (f"Posted {int(age * 24)}h ago" if age < 2 else f"Posted {int(age)} days ago")
    ok = age is None or age <= days
    c.append(("Posted", ok and not (age and age > 60), lab if ok else (f"Open for {int(age)} days" if age > 60 else f"{lab}; your window is {days} days."), ""))
    c.append(("Open", not f.get("closedQuote"), "Open" if not f.get("closedQuote") else "The posting says it's closed.", f.get("closedQuote") or ""))
    lc, lq = f.get("loc", "unknown"), f.get("locQuote") or r.get("location", "")
    region = {"remote-worldwide": "remote-global", "remote-open": "remote-global", "remote-unclear": "remote-global",
              "remote-india": "remote-india", "south": "south-india", "india": "south-india", "unknown": "south-india"}.get(lc, "")
    lok = bool(region) and not (region == "remote-global" and abroad == "never") and not (lc == "remote-india" and rest == "never" and r.get("geo") != "south") \
        and not (lc == "south" and south != "any") and not (lc == "india" and rest != "any")
    lv = {"remote-worldwide": "Remote worldwide", "remote-open": "Remote, open to India", "remote-unclear": "Remote; the posting doesn't say who can apply. Check before applying.",
          "remote-india": "Remote, India", "south": "South India", "india": r.get("location", ""), "unknown": "Location not stated. Check before applying.",
          "remote-excluded": "Remote, but not open to people in India.", "abroad": "On-site or hybrid abroad."}.get(lc, lc)
    c.append(("Location", lok, lv if lok else (lv if lc in ("remote-excluded", "abroad") else "Outside your locations."), lq))
    hi = f.get("salaryHigh")
    c.append(("Pay", not (floor and hi is not None and hi < floor), "Not stated" if hi is None else f"{f.get('salaryLow', hi):g}–{hi:g} LPA", f.get("salaryQuote") or ""))
    m = next((re.search(re.escape(w), r.get("summary") or "", re.I) for w in deal if re.search(re.escape(w), r.get("summary") or "", re.I)), None)
    c.append(("Dealbreaker", m is None, "None found" if m is None else f"Mentions '{m.group(0)}'.", ""))
    return c, region if lok else "", age

kept, skipped, seen, feed_urls = [], [], set(), set()
for line in gzip.open(feed_p, "rt", encoding="utf-8"):
    if not line.strip(): continue
    r = json.loads(line); k = fp(r["company"], r["title"]); feed_urls.add(curl(r["url"]))
    if r["id"] in ids or curl(r["url"]) in urls or k in fps or k in seen: continue
    checks, region, age = decide(r)
    failed = [g for g, ok, _, _ in checks if not ok]
    near = len(failed) == 1 and failed[0] in ("Experience", "Posted", "Location", "Pay", "Seniority")
    if failed and not near: continue
    seen.add(k); board = r.get("via") == "board"
    doc = {"company": r["company"], "title": r["title"], "url": r["url"], "source": r["source"] if board else r["source"] + " (company careers page)",
           "location": r.get("location", ""), "workMode": r.get("workMode", ""), "postedAt": r.get("postedAt", ""), "salary": r.get("salary", ""),
           "region": region, "priority": bool(region and age is not None and age <= 2), "stage": "skipped" if failed else "found", "fitBand": "pending",
           "foundAt": iso(now), "foundVia": "remote-board" if board else "careers-feed", "experience": checks[3][2],
           "checks": [{"gate": g, "passed": ok, "value": v, "quote": q[:200]} for g, ok, v, q in checks],
           "timeline": [{"at": iso(now), "event": "Found on " + r["source"]}],
           "brief": {"about": (re.match(r"(.{40,260}?[.!?])\s", (r.get("summary") or "") + " ") or [None, (r.get("summary") or "")[:240]])[1],
                     "sources": [{"title": (r["source"] + " listing") if board else (r["company"] + " careers page"), "url": r["url"]}]}}
    if (r.get("facts") or {}).get("applicants"): doc["applicants"] = r["facts"]["applicants"]
    if failed:
        g = failed[0]; v = next(x for x in checks if x[0] == g)
        doc["skip"] = {"gate": g, "reason": v[2] + (f' The posting says: "{v[3][:200]}"' if v[3] else ""),
                       "wouldChange": {"Experience": "Raising your experience limit.", "Posted": "A wider posting window.", "Location": "Allowing this location or work mode.",
                                       "Pay": "A lower pay floor.", "Seniority": "Allowing senior titles."}[g]}
        skipped.append((r["id"], doc))
    else:
        kept.append((r["id"], doc))
order = {"remote-global": 0, "remote-india": 1, "south-india": 2}
def ts(s):
    try: d = datetime.fromisoformat((s or "").replace("Z", "+00:00")); return (d if d.tzinfo else d.replace(tzinfo=timezone.utc)).timestamp()
    except ValueError: return 0
kept.sort(key=lambda x: (order.get(x[1]["region"], 9), -ts(x[1]["postedAt"])))
for sub, items in (("kept", kept[:max_kept]), ("skipped", skipped[:max_skips])):
    os.makedirs(os.path.join(out_p, sub), exist_ok=True)
    for i, d in items: json.dump(d, open(os.path.join(out_p, sub, i[:150] + ".json"), "w"), ensure_ascii=False)
# Roles on the dashboard that the feed shows closed (gone) or posted before the window (expired).
gone, expired, errored = [], [], set((summary or {}).get("erroredCompanies", []))
for i, d in known:
    if d.get("stage") not in ("found", None, ""): continue
    if d.get("postedAt") and ts(d["postedAt"]) and (now.timestamp() - ts(d["postedAt"])) / 86400 > days: expired.append(i); continue
    if summary and d.get("foundVia") in ("careers-feed", "remote-board") and d.get("url") and curl(d["url"]) not in feed_urls and d.get("company") not in errored: gone.append(i)
json.dump({"kept": [i for i, _ in kept[:max_kept]], "skipped": [i for i, _ in skipped[:max_skips]], "gone": gone, "expired": expired},
          open(os.path.join(out_p, "index.json"), "w"), indent=1)
print(json.dumps({"gone": len(gone), "expired": len(expired), "kept": len(kept[:max_kept]), "skipped": len(skipped[:max_skips]), "byRegion": {k: sum(1 for _, d in kept[:max_kept] if d["region"] == k) for k in order}}))
