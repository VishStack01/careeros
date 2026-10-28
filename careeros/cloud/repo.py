"""Data access for the cloud service. Every per-person query takes a user id and
filters by it, so a record from another account is simply "not found"."""

from __future__ import annotations

import json
from datetime import timedelta

from ..store import merge
from .db import Conn, now_iso
from .security import new_id, new_token, token_hash

COLLECTIONS = {"jobs", "runs", "settings", "brain", "profile", "inbox"}
DEFAULT_SETTINGS = {
    "targetRoles": [], "titleExclude": [], "locations": ["South India (any work mode)", "Rest of India (remote only)", "Remote worldwide (first priority)"],
    "experienceLevels": ["Fresher", "1+ years"], "maxRequiredYears": 1, "maxPostingAgeDays": 25, "salaryFloorLpa": "",
    "dailyCap": 8, "minFit": "good", "approvalMode": "daily-batch", "dealbreakers": "", "noticeDays": "",
    "schedule": "Matched every hour against the shared job inventory",
}


def _j(x) -> str:
    return json.dumps(x, ensure_ascii=False, separators=(",", ":"))


# ------------------------------------------------------------------ users
def create_user(c: Conn, email: str, name: str, password_hash: str, is_admin: bool = False) -> str:
    uid, now = new_id(), now_iso()
    c.execute("INSERT INTO users(id, email, name, password_hash, is_admin, created_at, updated_at, password_changed_at) "
              "VALUES (?, ?, ?, ?, ?, ?, ?, ?)", (uid, email, name, password_hash, 1 if is_admin else 0, now, now, now))
    set_doc(c, uid, "settings", "profile", dict(DEFAULT_SETTINGS, updatedAt=now))
    set_doc(c, uid, "brain", "status", {"state": "waiting", "summary": "Upload your resume, then build your Career Brain.", "updatedAt": now})
    return uid


def user_by_email(c: Conn, email: str) -> dict | None:
    return c.one("SELECT * FROM users WHERE email = ?", (email,))


def user_by_id(c: Conn, uid: str) -> dict | None:
    return c.one("SELECT * FROM users WHERE id = ?", (uid,))


def public_user(u: dict) -> dict:
    return {"id": u["id"], "email": u["email"], "name": u["name"], "emailVerified": bool(u["email_verified_at"]),
            "isAdmin": bool(u["is_admin"]), "createdAt": u["created_at"]}


def audit(c: Conn, user_id: str | None, kind: str, ip: str = "", detail: dict | None = None) -> None:
    c.execute("INSERT INTO audit_events(id, user_id, at, kind, ip, detail) VALUES (?, ?, ?, ?, ?, ?)",
              (new_id(), user_id, now_iso(), kind, ip[:64], _j(detail or {})))


# ------------------------------------------------------------------ sessions
def create_session(c: Conn, uid: str, ttl_days: int, ip: str, ua: str) -> str:
    token, now = new_token("cos_s_"), now_iso()
    c.execute("INSERT INTO sessions(id, user_id, token_hash, created_at, expires_at, last_seen_at, ip, user_agent) "
              "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
              (new_id(), uid, token_hash(token), now, now_iso(timedelta(days=ttl_days)), now, ip[:64], ua[:200]))
    c.execute("UPDATE users SET last_login_at = ? WHERE id = ?", (now, uid))
    return token


def session_user(c: Conn, token: str) -> tuple[dict, dict] | None:
    row = c.one("SELECT s.id AS session_id, s.last_seen_at, s.expires_at, u.* FROM sessions s JOIN users u ON u.id = s.user_id "
                "WHERE s.token_hash = ? AND s.revoked_at IS NULL AND s.expires_at > ? AND u.disabled_at IS NULL",
                (token_hash(token), now_iso()))
    if not row:
        return None
    if row["last_seen_at"] < now_iso(timedelta(minutes=-10)):
        c.execute("UPDATE sessions SET last_seen_at = ? WHERE id = ?", (now_iso(), row["session_id"]))
    return row, {"kind": "session", "id": row["session_id"], "scopes": {"all"}}


def revoke_session(c: Conn, token: str) -> None:
    c.execute("UPDATE sessions SET revoked_at = ? WHERE token_hash = ? AND revoked_at IS NULL", (now_iso(), token_hash(token)))


def revoke_all_sessions(c: Conn, uid: str, except_id: str | None = None) -> None:
    c.execute("UPDATE sessions SET revoked_at = ? WHERE user_id = ? AND revoked_at IS NULL AND id <> ?", (now_iso(), uid, except_id or ""))


# ------------------------------------------------------------------ computer keys (API tokens)
def create_api_token(c: Conn, uid: str, name: str, scopes: str = "agent") -> tuple[str, dict]:
    token, tid, now = new_token("cos_k_"), new_id(), now_iso()
    c.execute("INSERT INTO api_tokens(id, user_id, name, token_hash, prefix, scopes, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
              (tid, uid, name[:60], token_hash(token), token[:12], scopes, now))
    return token, {"id": tid, "name": name[:60], "prefix": token[:12], "createdAt": now, "lastUsedAt": None}


def list_api_tokens(c: Conn, uid: str) -> list[dict]:
    rows = c.all("SELECT id, name, prefix, created_at, last_used_at FROM api_tokens WHERE user_id = ? AND revoked_at IS NULL ORDER BY created_at", (uid,))
    return [{"id": r["id"], "name": r["name"], "prefix": r["prefix"], "createdAt": r["created_at"], "lastUsedAt": r["last_used_at"]} for r in rows]


def revoke_api_token(c: Conn, uid: str, tid: str) -> bool:
    cur = c.execute("UPDATE api_tokens SET revoked_at = ? WHERE id = ? AND user_id = ? AND revoked_at IS NULL", (now_iso(), tid, uid))
    return cur.rowcount > 0


def api_token_user(c: Conn, token: str) -> tuple[dict, dict] | None:
    row = c.one("SELECT t.id AS token_id, t.scopes, t.last_used_at AS token_used, u.* FROM api_tokens t JOIN users u ON u.id = t.user_id "
                "WHERE t.token_hash = ? AND t.revoked_at IS NULL AND (t.expires_at IS NULL OR t.expires_at > ?) AND u.disabled_at IS NULL",
                (token_hash(token), now_iso()))
    if not row:
        return None
    if not row["token_used"] or row["token_used"] < now_iso(timedelta(minutes=-10)):
        c.execute("UPDATE api_tokens SET last_used_at = ? WHERE id = ?", (now_iso(), row["token_id"]))
    return row, {"kind": "key", "id": row["token_id"], "scopes": set(row["scopes"].split())}


# ------------------------------------------------------------------ one-time links
def issue_link_token(c: Conn, uid: str, purpose: str, ttl: timedelta) -> str:
    token = new_token("")
    c.execute("UPDATE one_time_tokens SET used_at = ? WHERE user_id = ? AND purpose = ? AND used_at IS NULL", (now_iso(), uid, purpose))
    c.execute("INSERT INTO one_time_tokens(token_hash, user_id, purpose, created_at, expires_at) VALUES (?, ?, ?, ?, ?)",
              (token_hash(token), uid, purpose, now_iso(), now_iso(ttl)))
    return token


def consume_link_token(c: Conn, token: str, purpose: str) -> str | None:
    row = c.one("SELECT user_id FROM one_time_tokens WHERE token_hash = ? AND purpose = ? AND used_at IS NULL AND expires_at > ?",
                (token_hash(token or ""), purpose, now_iso()))
    if not row:
        return None
    c.execute("UPDATE one_time_tokens SET used_at = ? WHERE token_hash = ?", (now_iso(), token_hash(token)))
    return row["user_id"]


# ------------------------------------------------------------------ documents
def _doc(r: dict) -> dict:
    return {"id": r["id"], "data": json.loads(r["data"]), "version": r["version"]}


def list_docs(c: Conn, uid: str, col: str) -> list[dict]:
    return [_doc(r) for r in c.all("SELECT id, data, version FROM docs WHERE user_id = ? AND collection = ? ORDER BY id", (uid, col))]


def docs_etag(c: Conn, uid: str, col: str) -> str:
    r = c.one("SELECT COUNT(*) AS n, MAX(updated_at) AS t, SUM(version) AS v FROM docs WHERE user_id = ? AND collection = ?", (uid, col))
    return f'W/"{r["n"]}-{r["v"] or 0}-{r["t"] or ""}"'


def get_doc(c: Conn, uid: str, col: str, did: str) -> dict | None:
    r = c.one("SELECT id, data, version FROM docs WHERE user_id = ? AND collection = ? AND id = ?", (uid, col, did))
    return _doc(r) if r else None


def set_doc(c: Conn, uid: str, col: str, did: str, data: dict, if_version: int | None = None) -> int:
    cur = c.one("SELECT version FROM docs WHERE user_id = ? AND collection = ? AND id = ?", (uid, col, did))
    if if_version is not None and (cur["version"] if cur else 0) != if_version:
        raise ValueError(f"{col}/{did} changed since version {if_version}")
    body, now = _j(data), now_iso()
    if cur:
        c.execute("UPDATE docs SET data = ?, version = ?, size_bytes = ?, updated_at = ? WHERE user_id = ? AND collection = ? AND id = ?",
                  (body, cur["version"] + 1, len(body.encode()), now, uid, col, did))
        return cur["version"] + 1
    c.execute("INSERT INTO docs(user_id, collection, id, data, version, size_bytes, created_at, updated_at) VALUES (?, ?, ?, ?, 1, ?, ?, ?)",
              (uid, col, did, body, len(body.encode()), now, now))
    return 1


def update_doc(c: Conn, uid: str, col: str, did: str, patch: dict, if_version: int | None = None) -> int:
    cur = get_doc(c, uid, col, did)
    if not cur:
        raise KeyError(f"{col}/{did}")
    if if_version is not None and cur["version"] != if_version:
        raise ValueError(f"{col}/{did} changed since version {if_version}")
    return set_doc(c, uid, col, did, merge(cur["data"], patch))


def delete_doc(c: Conn, uid: str, col: str, did: str) -> None:
    c.execute("DELETE FROM docs WHERE user_id = ? AND collection = ? AND id = ?", (uid, col, did))


def count_docs(c: Conn, uid: str) -> int:
    return int(c.scalar("SELECT COUNT(*) AS n FROM docs WHERE user_id = ?", (uid,)) or 0)


def append_timeline(data: dict, event: str) -> list:
    return (list(data.get("timeline") or []) + [{"at": now_iso()[:19] + "Z", "event": event}])[-60:]


# ------------------------------------------------------------------ assets
def list_assets(c: Conn, uid: str) -> list[dict]:
    return c.all("SELECT id, name, content_type, size_bytes, created_at FROM assets WHERE user_id = ? ORDER BY created_at", (uid,))


def storage_used(c: Conn, uid: str) -> int:
    return int(c.scalar("SELECT COALESCE(SUM(size_bytes), 0) AS n FROM assets WHERE user_id = ?", (uid,)) or 0)


def get_asset(c: Conn, uid: str, aid: str) -> dict | None:
    return c.one("SELECT * FROM assets WHERE id = ? AND user_id = ?", (aid, uid))


# ------------------------------------------------------------------ tasks
def enqueue(c: Conn, kind: str, payload: dict | None = None, user_id: str | None = None, dedupe_key: str | None = None,
            delay_seconds: int = 0, max_attempts: int = 5) -> bool:
    """Queue a task. With a dedupe key, a second copy is dropped while one is queued or running."""
    now = now_iso()
    cur = c.execute("INSERT INTO tasks(id, kind, user_id, payload, dedupe_key, status, attempts, max_attempts, run_after, created_at, updated_at) "
                    "VALUES (?, ?, ?, ?, ?, 'queued', 0, ?, ?, ?, ?) ON CONFLICT DO NOTHING",
                    (new_id(), kind, user_id, _j(payload or {}), dedupe_key, max_attempts, now_iso(timedelta(seconds=delay_seconds)), now, now))
    return cur.rowcount > 0
