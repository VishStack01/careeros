"""Durable local state in one SQLite file.

* `docs` holds every record as a JSON document in a collection, the same shape
  the dashboard reads (jobs, runs, settings, brain). The hosted dashboard uses
  an identical document model, so data moves between the two unchanged.
* `job_keys` makes discovery idempotent: a role reposted on five boards is one
  record.
* `applications` is the submission state machine. Its idempotency key means a
  retry, a crash or a second scheduled run can never submit twice.
* `events` is the append-only audit log.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .dedupe import canonical_url, company_key, fingerprint, job_id
from .models import Job, iso

SCHEMA = """
CREATE TABLE IF NOT EXISTS docs (
  collection TEXT NOT NULL, id TEXT NOT NULL, data TEXT NOT NULL,
  version INTEGER NOT NULL DEFAULT 1, updated_at TEXT NOT NULL,
  PRIMARY KEY (collection, id)
);
CREATE TABLE IF NOT EXISTS job_keys (
  key TEXT PRIMARY KEY, job_id TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS applications (
  key TEXT PRIMARY KEY, job_id TEXT NOT NULL, company_key TEXT NOT NULL,
  state TEXT NOT NULL, attempts INTEGER NOT NULL DEFAULT 0,
  receipt TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS events (
  id INTEGER PRIMARY KEY AUTOINCREMENT, at TEXT NOT NULL,
  collection TEXT, doc_id TEXT, kind TEXT NOT NULL, detail TEXT
);
CREATE TABLE IF NOT EXISTS flags (name TEXT PRIMARY KEY, value TEXT);
"""


class AlreadySubmitted(RuntimeError):
    """This application was already submitted. Never submit it again."""


class NeedsHumanCheck(RuntimeError):
    """A previous attempt stopped mid-submit. A person must check the site before any retry."""


class Paused(RuntimeError):
    """The kill switch is on."""


def _now() -> str:
    return iso(datetime.now(timezone.utc))


def merge(base: dict, patch: dict) -> dict:
    """Deep-merge `patch` into `base`. Objects merge, everything else replaces.
    A value of {"__delete__": true} removes the key."""
    out = dict(base)
    for k, v in patch.items():
        if isinstance(v, dict) and v.get("__delete__") is True:
            out.pop(k, None)
        elif isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = merge(out[k], v)
        else:
            out[k] = v
    return out


class Store:
    def __init__(self, path: str | Path = "data/careeros.db"):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(self.path, check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        self.db.executescript(SCHEMA)

    @contextmanager
    def tx(self):
        try:
            yield self.db
            self.db.commit()
        except Exception:
            self.db.rollback()
            raise

    # ------------------------------------------------------------ documents
    def get(self, collection: str, doc_id: str) -> dict | None:
        row = self.db.execute("SELECT data, version FROM docs WHERE collection=? AND id=?", (collection, doc_id)).fetchone()
        return {"id": doc_id, "data": json.loads(row["data"]), "version": row["version"]} if row else None

    def list(self, collection: str) -> list[dict]:
        rows = self.db.execute("SELECT id, data, version FROM docs WHERE collection=? ORDER BY id", (collection,)).fetchall()
        return [{"id": r["id"], "data": json.loads(r["data"]), "version": r["version"]} for r in rows]

    def set(self, collection: str, doc_id: str, data: dict, event: str = "set") -> int:
        with self.tx():
            cur = self.get(collection, doc_id)
            version = (cur["version"] + 1) if cur else 1
            self.db.execute(
                "INSERT INTO docs(collection,id,data,version,updated_at) VALUES(?,?,?,?,?) "
                "ON CONFLICT(collection,id) DO UPDATE SET data=excluded.data, version=excluded.version, updated_at=excluded.updated_at",
                (collection, doc_id, json.dumps(data, ensure_ascii=False), version, _now()),
            )
            self._log(collection, doc_id, event, None)
        return version

    def update(self, collection: str, doc_id: str, patch: dict, if_version: int | None = None) -> int:
        cur = self.get(collection, doc_id)
        if not cur:
            raise KeyError(f"{collection}/{doc_id} does not exist")
        if if_version is not None and cur["version"] != if_version:
            raise ValueError(f"{collection}/{doc_id} changed (now version {cur['version']})")
        with self.tx():
            version = cur["version"] + 1
            self.db.execute(
                "UPDATE docs SET data=?, version=?, updated_at=? WHERE collection=? AND id=?",
                (json.dumps(merge(cur["data"], patch), ensure_ascii=False), version, _now(), collection, doc_id),
            )
            self._log(collection, doc_id, "update", patch)
        return version

    def delete(self, collection: str, doc_id: str) -> None:
        with self.tx():
            self.db.execute("DELETE FROM docs WHERE collection=? AND id=?", (collection, doc_id))
            self._log(collection, doc_id, "delete", None)

    # ------------------------------------------------------------ jobs
    def add_job(self, job: Job) -> tuple[str, str]:
        """Insert a role unless we already know it. Returns ("new"|"known", id)."""
        keys = [k for k in (fingerprint(job.company, job.title), canonical_url(job.url)) if k]
        for k in keys:
            row = self.db.execute("SELECT job_id FROM job_keys WHERE key=?", (k,)).fetchone()
            if row:
                return "known", row["job_id"]
        base = job.id or job_id(job.company, job.title)
        doc_id, n = base, 2
        while self.get("jobs", doc_id):
            doc_id, n = f"{base}-{n}", n + 1
        job.id = doc_id
        with self.tx():
            for k in keys:
                self.db.execute("INSERT OR IGNORE INTO job_keys(key, job_id) VALUES(?,?)", (k, doc_id))
        self.set("jobs", doc_id, job.to_record(), event="found" if job.stage == "found" else "skipped")
        return "new", doc_id

    # ------------------------------------------------------------ applications
    @staticmethod
    def application_key(job: dict) -> str:
        basis = company_key(job.get("company", "")) + "|" + (canonical_url(job.get("url", "")) or fingerprint(job.get("company", ""), job.get("title", "")))
        return hashlib.sha256(basis.encode()).hexdigest()[:24]

    def applied_recently(self, company: str, days: int = 180) -> bool:
        since = iso(datetime.now(timezone.utc) - timedelta(days=days))
        row = self.db.execute(
            "SELECT 1 FROM applications WHERE company_key=? AND state='submitted' AND updated_at>=? LIMIT 1",
            (company_key(company), since),
        ).fetchone()
        return bool(row)

    def begin_submit(self, job_id_: str, job: dict) -> str:
        if self.flag("paused"):
            raise Paused("CareerOS is paused. Run `careeros resume` to continue.")
        key = self.application_key(job)
        row = self.db.execute("SELECT state FROM applications WHERE key=?", (key,)).fetchone()
        if row and row["state"] == "submitted":
            raise AlreadySubmitted(f"{job.get('company')} / {job.get('title')} was already submitted.")
        if row and row["state"] == "submitting":
            raise NeedsHumanCheck("A previous attempt stopped mid-submit. Check the company's site or your email before retrying.")
        now = _now()
        with self.tx():
            self.db.execute(
                "INSERT INTO applications(key,job_id,company_key,state,attempts,created_at,updated_at) VALUES(?,?,?,?,1,?,?) "
                "ON CONFLICT(key) DO UPDATE SET state='submitting', attempts=attempts+1, updated_at=excluded.updated_at",
                (key, job_id_, company_key(job.get("company", "")), "submitting", now, now),
            )
            self._log("applications", job_id_, "submit-start", {"key": key})
        return key

    def finish_submit(self, key: str, ok: bool, receipt: dict) -> None:
        with self.tx():
            self.db.execute(
                "UPDATE applications SET state=?, receipt=?, updated_at=? WHERE key=?",
                ("submitted" if ok else "failed", json.dumps(receipt, ensure_ascii=False), _now(), key),
            )
            self._log("applications", receipt.get("job_id"), "submitted" if ok else "submit-failed", receipt)

    def clear_stuck(self, key: str) -> None:
        """After a human confirmed a stuck attempt did NOT go through."""
        with self.tx():
            self.db.execute("UPDATE applications SET state='failed', updated_at=? WHERE key=? AND state='submitting'", (_now(), key))

    # ------------------------------------------------------------ flags & audit
    def flag(self, name: str) -> bool:
        row = self.db.execute("SELECT value FROM flags WHERE name=?", (name,)).fetchone()
        return bool(row and row["value"] == "1")

    def set_flag(self, name: str, on: bool) -> None:
        with self.tx():
            self.db.execute("INSERT INTO flags(name,value) VALUES(?,?) ON CONFLICT(name) DO UPDATE SET value=excluded.value", (name, "1" if on else "0"))
            self._log("flags", name, "on" if on else "off", None)

    def _log(self, collection, doc_id, kind, detail) -> None:
        self.db.execute(
            "INSERT INTO events(at,collection,doc_id,kind,detail) VALUES(?,?,?,?,?)",
            (_now(), collection, doc_id, kind, json.dumps(detail, ensure_ascii=False) if detail is not None else None),
        )

    def events(self, limit: int = 50) -> list[dict]:
        rows = self.db.execute("SELECT * FROM events ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
        return [dict(r) for r in rows]
