"""One small database layer for SQLite (development, tests) and PostgreSQL (production).

SQL is written once with `?` placeholders and portable types (TEXT ids and
ISO-8601 UTC timestamps, JSON stored as TEXT, INTEGER booleans). For
PostgreSQL the placeholders become `%s`. Rows come back as dicts.

    with db.tx() as c:
        c.execute("UPDATE ... WHERE id = ?", (x,))
        row = c.one("SELECT ... WHERE id = ?", (x,))
"""

from __future__ import annotations

import re
import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterator

MIGRATIONS = Path(__file__).resolve().parent / "migrations"


def now_iso(delta: timedelta | None = None) -> str:
    t = datetime.now(timezone.utc) + (delta or timedelta())
    return t.strftime("%Y-%m-%dT%H:%M:%S.%fZ")


class Conn:
    """A transaction-scoped connection with dict rows."""

    def __init__(self, raw, kind: str):
        self.raw, self.kind = raw, kind

    def _sql(self, sql: str) -> str:
        if self.kind == "postgres":
            return sql.replace("%", "%%").replace("?", "%s")
        return sql.replace(" FOR UPDATE SKIP LOCKED", "")

    def execute(self, sql: str, params: tuple | list = ()) -> Any:
        cur = self.raw.cursor()
        cur.execute(self._sql(sql), tuple(params))
        return cur

    def many(self, sql: str, rows: list[tuple]) -> None:
        if rows:
            self.raw.cursor().executemany(self._sql(sql), rows)

    def all(self, sql: str, params: tuple | list = ()) -> list[dict]:
        cur = self.execute(sql, params)
        return [dict(r) for r in cur.fetchall()]

    def one(self, sql: str, params: tuple | list = ()) -> dict | None:
        cur = self.execute(sql, params)
        r = cur.fetchone()
        return dict(r) if r is not None else None

    def scalar(self, sql: str, params: tuple | list = ()) -> Any:
        r = self.one(sql, params)
        return next(iter(r.values())) if r else None


class Database:
    def __init__(self, url: str, pool_min: int = 1, pool_max: int = 10):
        self.url = url
        if url.startswith("sqlite:"):
            self.kind = "sqlite"
            self.path = url.split("sqlite:///", 1)[-1] if "sqlite:///" in url else url.split("sqlite:", 1)[-1]
            Path(self.path).parent.mkdir(parents=True, exist_ok=True)
            self._lock = threading.RLock()
            with self._sqlite() as raw:
                raw.execute("PRAGMA journal_mode=WAL")
        elif url.startswith(("postgres://", "postgresql://")):
            self.kind = "postgres"
            from psycopg.rows import dict_row
            from psycopg_pool import ConnectionPool
            self.pool = ConnectionPool(url, min_size=pool_min, max_size=pool_max, timeout=10,
                                       kwargs={"row_factory": dict_row, "autocommit": False}, open=True)
        else:
            raise ValueError("DATABASE_URL must start with sqlite:/// or postgresql://")

    def _sqlite(self):
        raw = sqlite3.connect(self.path, timeout=30, isolation_level=None, check_same_thread=False)
        raw.row_factory = sqlite3.Row
        raw.execute("PRAGMA foreign_keys=ON")
        raw.execute("PRAGMA busy_timeout=30000")
        return raw

    @contextmanager
    def tx(self) -> Iterator[Conn]:
        if self.kind == "sqlite":
            # One writer at a time: BEGIN IMMEDIATE takes the write lock up front,
            # so read-then-write sequences never deadlock or interleave.
            with self._lock:
                raw = self._sqlite()
                try:
                    raw.execute("BEGIN IMMEDIATE")
                    yield Conn(raw, "sqlite")
                    raw.execute("COMMIT")
                except BaseException:
                    raw.execute("ROLLBACK")
                    raise
                finally:
                    raw.close()
        else:
            with self.pool.connection() as raw:
                try:
                    yield Conn(raw, "postgres")
                    raw.commit()
                except BaseException:
                    raw.rollback()
                    raise

    def close(self) -> None:
        if self.kind == "postgres":
            self.pool.close()

    # ------------------------------------------------------------ migrations
    def _files(self) -> list[tuple[str, Path]]:
        out = []
        for f in sorted(MIGRATIONS.glob("*.sql")):
            parts = f.name.split(".")
            if len(parts) == 3 and parts[1] != self.kind:  # 0002_x.postgres.sql runs on PostgreSQL only
                continue
            out.append((parts[0], f))
        return out

    def pending_migrations(self) -> list[str]:
        with self.tx() as c:
            c.execute("CREATE TABLE IF NOT EXISTS schema_migrations (version TEXT PRIMARY KEY, applied_at TEXT NOT NULL)")
            done = {r["version"] for r in c.all("SELECT version FROM schema_migrations")}
        return [v for v, _ in self._files() if v not in done]

    def migrate(self, log=print) -> list[str]:
        applied = []
        for version, f in self._files():
            with self.tx() as c:
                c.execute("CREATE TABLE IF NOT EXISTS schema_migrations (version TEXT PRIMARY KEY, applied_at TEXT NOT NULL)")
                if c.one("SELECT 1 AS x FROM schema_migrations WHERE version = ?", (version,)):
                    continue
                for stmt in _statements(f.read_text(encoding="utf-8")):
                    c.execute(stmt) if self.kind == "postgres" else c.raw.execute(stmt)
                c.execute("INSERT INTO schema_migrations(version, applied_at) VALUES (?, ?)", (version, now_iso()))
            applied.append(version)
            log(f"applied migration {f.name}")
        return applied


def _statements(sql: str) -> list[str]:
    sql = re.sub(r"--[^\n]*", "", sql)
    return [s.strip() for s in sql.split(";") if s.strip()]
