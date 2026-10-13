"""Passwords, tokens, rate limits and input checks. Standard library only."""

from __future__ import annotations

import base64
import hashlib
import hmac
import re
import secrets
import uuid
from datetime import datetime, timedelta, timezone

from .db import Conn

ALGO = "pbkdf2_sha256"
_EMAIL = re.compile(r"^[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+@[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?(?:\.[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?)+$")
# A short list of the passwords people pick most; length rules do most of the work.
_COMMON = {
    "password", "password1", "password123", "1234567890", "12345678910", "qwertyuiop", "iloveyou12", "letmein123",
    "welcome123", "admin12345", "qwerty1234", "abc1234567", "1q2w3e4r5t", "passw0rd12", "india12345", "careeros123",
}


def new_id() -> str:
    return uuid.uuid4().hex


def normalize_email(email: str) -> str:
    return (email or "").strip().lower()


def valid_email(email: str) -> bool:
    return len(email) <= 254 and bool(_EMAIL.match(email))


def password_problem(password: str, email: str = "") -> str | None:
    """Why a password is unacceptable, or None."""
    if not isinstance(password, str) or len(password) < 10:
        return "Use at least 10 characters."
    if len(password) > 128:
        return "Use at most 128 characters."
    low = password.lower()
    if low in _COMMON or len(set(low)) < 4:
        return "That password is too easy to guess."
    local = email.split("@", 1)[0].lower() if email else ""
    if len(local) >= 4 and local in low:
        return "Don't use your email address in your password."
    return None


def hash_password(password: str, iterations: int) -> str:
    salt = secrets.token_bytes(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, iterations)
    return f"{ALGO}${iterations}${base64.b64encode(salt).decode()}${base64.b64encode(dk).decode()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        algo, it, salt, dk = stored.split("$")
        if algo != ALGO:
            return False
        got = hashlib.pbkdf2_hmac("sha256", password.encode(), base64.b64decode(salt), int(it))
        return hmac.compare_digest(got, base64.b64decode(dk))
    except (ValueError, TypeError):
        return False


def needs_rehash(stored: str, iterations: int) -> bool:
    try:
        return int(stored.split("$")[1]) < iterations
    except (IndexError, ValueError):
        return True


def dummy_verify(iterations: int) -> None:
    """Spend the same time as a real check, so unknown emails can't be told apart by timing."""
    hashlib.pbkdf2_hmac("sha256", b"x", b"careeros-dummy-salt", iterations)


def new_token(prefix: str) -> str:
    return prefix + secrets.token_urlsafe(32)


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def hit(c: Conn, key: str, limit: int, window_seconds: int) -> bool:
    """Count one attempt against `key`. False when the limit for this window is used up.
    Fixed windows stored in the database, so every API replica shares them."""
    now = datetime.now(timezone.utc)
    start = datetime.fromtimestamp(int(now.timestamp()) // window_seconds * window_seconds, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    c.execute("INSERT INTO rate_limits(key, window_start, count) VALUES (?, ?, 1) "
              "ON CONFLICT (key, window_start) DO UPDATE SET count = rate_limits.count + 1", (key, start))
    n = c.scalar("SELECT count FROM rate_limits WHERE key = ? AND window_start = ?", (key, start))
    return int(n or 0) <= limit


def ip_key(ip: str) -> str:
    """Rate-limit keys never store raw addresses."""
    return hashlib.sha256(("careeros-ip|" + (ip or "")).encode()).hexdigest()[:24]


def iso(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def later(**kw) -> str:
    return iso(datetime.now(timezone.utc) + timedelta(**kw))
