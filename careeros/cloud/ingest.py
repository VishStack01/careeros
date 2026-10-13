"""Read the hourly scan's feed into the shared `jobs` table.

Fails closed: an empty, unreadable or suspiciously small feed changes nothing,
so a bad scan can never wipe the inventory. A role is closed only when its
company's board was read successfully and no longer lists it.
"""

from __future__ import annotations

import gzip
import json
import urllib.request
from pathlib import Path

from .db import Database, now_iso

MAX_BYTES = 200 * 1024 * 1024


class IngestError(RuntimeError):
    pass


def _fetch(base: str, name: str) -> bytes | None:
    src = base.rstrip("/") + "/" + name
    try:
        if src.startswith(("http://", "https://")):
            req = urllib.request.Request(src, headers={"User-Agent": "careeros-cloud"})
            with urllib.request.urlopen(req, timeout=120) as r:
                raw = r.read(MAX_BYTES + 1)
        else:
            raw = Path(src).read_bytes()
    except (OSError, ValueError):
        return None
    if len(raw) > MAX_BYTES:
        raise IngestError(f"{name} is larger than {MAX_BYTES // 1024 // 1024} MB")
    return raw


def _jsonl(raw: bytes | None) -> list[dict]:
    if not raw:
        return []
    if raw[:2] == b"\x1f\x8b":
        raw = gzip.decompress(raw)
    out = []
    for line in raw.decode("utf-8").splitlines():
        if line.strip():
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return out


def load(base: str) -> tuple[list[dict], dict[str, str], dict]:
    records = _jsonl(_fetch(base, "india.jsonl.gz"))
    texts = {t["id"]: t.get("text", "") for t in _jsonl(_fetch(base, "full.jsonl.gz")) if t.get("id")}
    raw = _fetch(base, "summary.json")
    try:
        summary = json.loads(raw) if raw else {}
    except json.JSONDecodeError:
        summary = {}
    return records, texts, summary


def ingest(db: Database, feed_url: str, log=print, force: bool = False) -> dict:
    records, texts, summary = load(feed_url)
    records = [r for r in records if r.get("id") and r.get("company") and r.get("title") and r.get("url") and "loc" in (r.get("facts") or {})]
    if not records:
        raise IngestError("The feed is empty or unreadable; keeping the current inventory.")
    if not summary.get("generatedAt"):
        raise IngestError("The feed has no summary.json; keeping the current inventory.")
    now = now_iso()
    with db.tx() as c:
        prev = c.one("SELECT value FROM feed_state WHERE key = 'feed'")
        prev = json.loads(prev["value"]) if prev else {}
        if prev.get("generatedAt") == summary["generatedAt"] and not force:
            return {"status": "unchanged", "generatedAt": summary["generatedAt"]}
        active = c.all("SELECT id, company FROM jobs WHERE active = 1")
        if not force and len(active) > 200 and len(records) < 0.5 * len(active):
            raise IngestError(f"The feed shrank from {len(active)} to {len(records)} roles; keeping the current inventory until a scan confirms it.")
        rows = []
        for r in records:
            text = texts.get(r["id"], "")[:20000]
            rec = {k: v for k, v in r.items() if k != "text"}
            facts = dict(rec.get("facts") or {})
            if (facts.get("salaryHigh") or 0) > 450:  # no fresher role pays 450+ LPA: a funding or revenue figure misread as pay
                for k in ("salaryLow", "salaryHigh", "salaryQuote"):
                    facts.pop(k, None)
                rec["facts"] = facts
            rows.append((r["id"], r["company"][:200], r["title"][:300], r["url"][:2000], str(r.get("source", ""))[:100],
                         r.get("postedAt") or "", json.dumps(rec, ensure_ascii=False, separators=(",", ":")), text, now, now))
        c.many("INSERT INTO jobs(id, company, title, url, source, posted_at, record, text, active, first_seen_at, last_seen_at) "
               "VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?) ON CONFLICT (id) DO UPDATE SET company = excluded.company, title = excluded.title, "
               "url = excluded.url, source = excluded.source, posted_at = excluded.posted_at, record = excluded.record, text = excluded.text, "
               "active = 1, last_seen_at = excluded.last_seen_at, closed_at = NULL", rows)
        seen = {r["id"] for r in records}
        errored = set(summary.get("erroredCompanies") or [])
        closing = [(now, a["id"]) for a in active if a["id"] not in seen and a["company"] not in errored]
        c.many("UPDATE jobs SET active = 0, closed_at = ? WHERE id = ?", closing)
        state = {k: summary.get(k) for k in ("generatedAt", "companies", "boards", "openings", "remoteBoards", "erroredCompanies")}
        state.update(records=len(records), closed=len(closing), ingestedAt=now)
        c.execute("INSERT INTO feed_state(key, value, updated_at) VALUES ('feed', ?, ?) "
                  "ON CONFLICT (key) DO UPDATE SET value = excluded.value, updated_at = excluded.updated_at",
                  (json.dumps(state), now))
    log(f"ingested {len(records)} roles ({len(closing)} closed) from feed generated {summary['generatedAt']}")
    return {"status": "ingested", "records": len(records), "closed": len(closing), "generatedAt": summary["generatedAt"]}


def feed_state(c) -> dict:
    row = c.one("SELECT value FROM feed_state WHERE key = 'feed'")
    return json.loads(row["value"]) if row else {}
