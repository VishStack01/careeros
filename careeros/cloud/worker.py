"""The background worker: a durable task queue in the database.

Tasks are claimed with a lease (`FOR UPDATE SKIP LOCKED` on PostgreSQL, a
single-writer transaction on SQLite), retried with exponential backoff, and
deduplicated while queued or running. Several workers can run at once.

Scheduled work:
  ingest       every INGEST_EVERY_MINUTES: read the hourly scan into the shared inventory,
               then queue a match for every verified account
  match_user   one account's filters against the inventory (also queued when settings change)
  send_email   verification, reset and notice emails, with retries
  cleanup      daily: expired sessions and links, old tasks, rate-limit windows, long-closed roles
"""

from __future__ import annotations

import json
import logging
import os
import socket
import threading
import time
from datetime import timedelta

from . import repo
from .config import Config
from .db import Database, now_iso
from .ingest import IngestError, ingest
from .mailer import Mailer
from .matching import match_user

log = logging.getLogger("careeros.worker")


class Worker:
    def __init__(self, cfg: Config, db: Database, mailer: Mailer | None = None, worker_id: str | None = None):
        self.cfg, self.db = cfg, db
        self.mailer = mailer or Mailer(cfg.smtp_url, cfg.mail_from)
        self.id = worker_id or f"{socket.gethostname()}:{os.getpid()}"

    # ------------------------------------------------------------ scheduling
    def _due(self, c, key: str, every: timedelta) -> bool:
        row = c.one("SELECT value FROM feed_state WHERE key = ?", (key,))
        if row and row["value"] > now_iso():
            return False
        c.execute("INSERT INTO feed_state(key, value, updated_at) VALUES (?, ?, ?) "
                  "ON CONFLICT (key) DO UPDATE SET value = excluded.value, updated_at = excluded.updated_at",
                  (key, now_iso(every), now_iso()))
        return True

    def schedule(self) -> None:
        with self.db.tx() as c:
            if self._due(c, "next_ingest_at", timedelta(minutes=self.cfg.ingest_every_minutes)):
                repo.enqueue(c, "ingest", dedupe_key="ingest", max_attempts=3)
            if self._due(c, "next_cleanup_at", timedelta(hours=24)):
                repo.enqueue(c, "cleanup", dedupe_key="cleanup", max_attempts=2)

    # ------------------------------------------------------------ queue
    def claim(self) -> dict | None:
        now = now_iso()
        with self.db.tx() as c:
            return c.one(
                "UPDATE tasks SET status = 'running', locked_by = ?, locked_until = ?, attempts = attempts + 1, updated_at = ? "
                "WHERE id = (SELECT id FROM tasks WHERE (status = 'queued' AND run_after <= ?) OR (status = 'running' AND locked_until < ?) "
                "ORDER BY run_after LIMIT 1 FOR UPDATE SKIP LOCKED) RETURNING *",
                (self.id, now_iso(timedelta(minutes=self.cfg.worker_lease_minutes)), now, now, now))

    def finish(self, task: dict, error: str | None = None) -> None:
        now = now_iso()
        scrub = task["kind"] == "send_email"  # the payload holds a sign-in link: don't keep it
        with self.db.tx() as c:
            if error is None:
                c.execute("UPDATE tasks SET status = 'done', finished_at = ?, updated_at = ?, locked_until = NULL, last_error = NULL"
                          + (", payload = '{}'" if scrub else "") + " WHERE id = ? AND locked_by = ?", (now, now, task["id"], self.id))
            elif task["attempts"] >= task["max_attempts"]:
                c.execute("UPDATE tasks SET status = 'failed', finished_at = ?, updated_at = ?, locked_until = NULL, last_error = ?"
                          + (", payload = '{}'" if scrub else "") + " WHERE id = ? AND locked_by = ?", (now, now, error[:500], task["id"], self.id))
            else:
                backoff = timedelta(minutes=min(2 ** task["attempts"], 60))
                c.execute("UPDATE tasks SET status = 'queued', run_after = ?, updated_at = ?, locked_until = NULL, locked_by = NULL, last_error = ? "
                          "WHERE id = ? AND locked_by = ?", (now_iso(backoff), now, error[:500], task["id"], self.id))

    def run(self, task: dict) -> None:
        payload = json.loads(task["payload"] or "{}")
        try:
            if task["kind"] == "ingest":
                res = ingest(self.db, self.cfg.feed_url, log=log.info)
                if res["status"] == "ingested":
                    self.queue_matches()
            elif task["kind"] == "match_user":
                if task["user_id"]:
                    match_user(self.db, task["user_id"], log=log.info)
            elif task["kind"] == "send_email":
                self.mailer.send(payload["to"], payload["subject"], payload["text"])
            elif task["kind"] == "cleanup":
                cleanup(self.db)
            else:
                raise ValueError(f"unknown task kind {task['kind']}")
        except IngestError as e:
            log.warning("ingest held back: %s", e)
            self.finish(task, str(e))
            return
        except Exception as e:  # noqa: BLE001 - every failure is recorded on the task and retried
            log.exception("task %s (%s) failed", task["id"], task["kind"])
            self.finish(task, f"{type(e).__name__}: {e}")
            return
        self.finish(task)

    def queue_matches(self) -> int:
        n = 0
        with self.db.tx() as c:
            users = c.all("SELECT id FROM users WHERE email_verified_at IS NOT NULL AND disabled_at IS NULL")
            for u in users:
                n += repo.enqueue(c, "match_user", user_id=u["id"], dedupe_key=f"match:{u['id']}", max_attempts=3)
        return n

    def tick(self) -> bool:
        self.schedule()
        task = self.claim()
        if not task:
            return False
        self.run(task)
        return True

    def drain(self, limit: int = 1000) -> int:
        """Run every due task now (tests and one-off maintenance)."""
        n = 0
        while n < limit and self.tick():
            n += 1
        return n

    def run_forever(self, stop: threading.Event | None = None) -> None:
        stop = stop or threading.Event()
        log.info("worker %s started", self.id)
        while not stop.is_set():
            try:
                busy = self.tick()
            except Exception:  # noqa: BLE001 - a database blip must not kill the worker
                log.exception("worker tick failed")
                busy = False
            if not busy:
                stop.wait(self.cfg.worker_poll_seconds)


def cleanup(db: Database) -> dict:
    now = now_iso()
    with db.tx() as c:
        out = {
            "sessions": c.execute("DELETE FROM sessions WHERE expires_at < ? OR (revoked_at IS NOT NULL AND revoked_at < ?)", (now_iso(timedelta(days=-7)), now_iso(timedelta(days=-7)))).rowcount,
            "links": c.execute("DELETE FROM one_time_tokens WHERE expires_at < ? OR used_at IS NOT NULL", (now,)).rowcount,
            "rate": c.execute("DELETE FROM rate_limits WHERE window_start < ?", (now_iso(timedelta(days=-1))[:19] + "Z",)).rowcount,
            "tasks": c.execute("DELETE FROM tasks WHERE (status = 'done' AND finished_at < ?) OR (status = 'failed' AND finished_at < ?)",
                               (now_iso(timedelta(days=-14)), now_iso(timedelta(days=-30)))).rowcount,
            "jobs": c.execute("DELETE FROM jobs WHERE active = 0 AND closed_at < ?", (now_iso(timedelta(days=-60)),)).rowcount,
            "audit": c.execute("DELETE FROM audit_events WHERE at < ?", (now_iso(timedelta(days=-365)),)).rowcount,
        }
    log.info("cleanup %s", out)
    return out


def main(cfg: Config | None = None) -> None:
    cfg = cfg or Config.from_env()
    logging.basicConfig(level=logging.INFO, format='{"t":"%(asctime)s","level":"%(levelname)s","logger":"%(name)s","msg":%(message)r}')
    db = Database(cfg.database_url, cfg.db_pool_min, cfg.db_pool_max)
    if db.pending_migrations():
        raise SystemExit("Database migrations are pending. Run `careeros cloud migrate` first.")
    w = Worker(cfg, db)
    stop = threading.Event()
    try:
        import signal
        signal.signal(signal.SIGTERM, lambda *_: stop.set())
    except (ValueError, OSError):
        pass
    try:
        w.run_forever(stop)
    except KeyboardInterrupt:
        pass
    finally:
        db.close()
        time.sleep(0)
