"""Match one user's filters against the shared inventory and update their pipeline.

The same decisions as `careeros filter-feed` and the scheduled search prompt:
each kept role carries the quoted checks that kept it; near-misses go to the
skip log with what would change the decision; roles that closed or aged out
leave the "found" list.
"""

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timedelta, timezone

from .. import feed
from . import repo
from .db import Database, now_iso
from .ingest import feed_state

MAX_PIPELINE = 900  # found + skipped roles kept per user before new ones wait
_ID = re.compile(r"^[A-Za-z0-9_.:@+~-]{1,200}$")


def settings_hash(doc: dict) -> str:
    keys = ("targetRoles", "titleExclude", "locations", "maxRequiredYears", "maxPostingAgeDays", "salaryFloorLpa", "dealbreakers", "companyBlocklist")
    return hashlib.sha256(json.dumps({k: doc.get(k) for k in keys}, sort_keys=True, default=str).encode()).hexdigest()[:16]


def match_user(db: Database, uid: str, now: datetime | None = None, log=print) -> dict:
    now = now or datetime.now(timezone.utc)
    started = now_iso()
    with db.tx() as c:
        sdoc = repo.get_doc(c, uid, "settings", "profile")
        sdata = sdoc["data"] if sdoc else dict(repo.DEFAULT_SETTINGS)
        known = [(d["id"], d["data"]) for d in repo.list_docs(c, uid, "jobs")]
        records = [json.loads(r["record"]) for r in c.all("SELECT record FROM jobs WHERE active = 1")]
        state = feed_state(c)
    settings = feed.settings_from_dashboard(sdata)
    open_found = sum(1 for _, d in known if d.get("stage") in ("found", "skipped", None, ""))
    room = max(0, MAX_PIPELINE - open_found)
    res = feed.match(records, settings, known, state or None, now, max_kept=min(150, room), max_skips=min(40, max(0, room - 150)))
    known_ids = {i for i, _ in known}
    added = skipped = closed = expired = 0
    with db.tx() as c:
        for sub in ("kept", "skipped"):
            for did, doc in res[sub]:
                if did in known_ids or not _ID.match(did) or repo.get_doc(c, uid, "jobs", did):
                    continue
                repo.set_doc(c, uid, "jobs", did, doc)
                added += sub == "kept"
                skipped += sub == "skipped"
        for did in res["gone"]:
            cur = repo.get_doc(c, uid, "jobs", did)
            if cur and cur["data"].get("stage") in ("found", None, ""):
                d = cur["data"]
                repo.update_doc(c, uid, "jobs", did, {"stage": "skipped", "skip": {"gate": "Closed", "reason": "No longer listed on the company's job board.", "wouldChange": ""},
                                                      "timeline": repo.append_timeline(d, "Closed: no longer listed")})
                closed += 1
        for did in res["expired"]:
            cur = repo.get_doc(c, uid, "jobs", did)
            if cur and cur["data"].get("stage") in ("found", None, "") and cur["data"].get("autoApply") != "queued":
                repo.delete_doc(c, uid, "jobs", did)
                expired += 1
        # Housekeeping: skipped roles older than 30 days, and only the 60 newest runs.
        cutoff = (now - timedelta(days=30)).strftime("%Y-%m-%dT%H:%M:%SZ")
        for d in repo.list_docs(c, uid, "jobs"):
            if d["data"].get("stage") == "skipped" and (d["data"].get("foundAt") or "9") < cutoff:
                repo.delete_doc(c, uid, "jobs", d["id"])
        runs = sorted(repo.list_docs(c, uid, "runs"), key=lambda d: d["data"].get("startedAt") or "", reverse=True)
        for d in runs[59:]:
            repo.delete_doc(c, uid, "runs", d["id"])
        best = next((doc for _, doc in res["kept"] if doc.get("region") == "remote-global"), None)
        summary = (f"{added} new {'role' if added == 1 else 'roles'} matched your filters"
                   + (f"; best remote-worldwide: {best['title']} at {best['company']}" if best else "") + "."
                   if added else "No new roles matched your filters this hour.")
        rid = now.strftime("%Y-%m-%dT%H%M") + "-match"
        repo.set_doc(c, uid, "runs", rid, {"startedAt": started, "finishedAt": now_iso(), "kind": "search", "scanned": len(records),
                                            "added": added, "skipped": skipped, "closed": closed, "summary": summary})
        if sdoc:
            repo.update_doc(c, uid, "settings", "profile", {"coverage": {
                "companies": state.get("companies"), "companyBoards": state.get("boards"), "openings": state.get("openings"),
                "feedAt": state.get("generatedAt"), "inventory": len(records)}})
        c.execute("INSERT INTO match_state(user_id, settings_hash, last_match_at, last_feed_at) VALUES (?, ?, ?, ?) "
                  "ON CONFLICT (user_id) DO UPDATE SET settings_hash = excluded.settings_hash, last_match_at = excluded.last_match_at, "
                  "last_feed_at = excluded.last_feed_at", (uid, settings_hash(sdata), now_iso(), state.get("generatedAt") or ""))
    log(f"matched user {uid[:8]}: +{added} kept, +{skipped} skipped, {closed} closed, {expired} expired")
    return {"added": added, "skipped": skipped, "closed": closed, "expired": expired, "inventory": len(records)}
