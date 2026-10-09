"""Polite, thread-safe fetching: a minimum gap between requests to each host,
bounded retries with backoff, and fast failure on "not found"."""

from __future__ import annotations

import json
import threading
import time
import urllib.error
import urllib.request
from urllib.parse import urlparse

USER_AGENT = "careeros/0.2 (+https://github.com/VishStack01/careeros; job-search scout)"
MIN_INTERVAL = 1.0  # seconds between requests to the same host; discovery lowers it

_locks: dict[str, threading.Lock] = {}
_last: dict[str, float] = {}
_slow: dict[str, float] = {}  # per-host interval raised after a 429
_guard = threading.Lock()


class FetchError(RuntimeError):
    def __init__(self, msg: str, status: int | None = None):
        super().__init__(msg)
        self.status = status


def _wait_turn(host: str, interval: float) -> None:
    with _guard:
        lock = _locks.setdefault(host, threading.Lock())
    with lock:
        wait = _last.get(host, 0) + max(interval, _slow.get(host, 0.0)) - time.monotonic()
        if wait > 0:
            time.sleep(wait)
        _last[host] = time.monotonic()


def get_bytes(url: str, timeout: float = 20.0, retries: int = 2, interval: float | None = None,
              accept: str = "application/json", data: bytes | None = None) -> bytes:
    host = urlparse(url).netloc
    delay = 1.5
    last: Exception | None = None
    status = None
    for attempt in range(retries + 1):
        _wait_turn(host, MIN_INTERVAL if interval is None else interval)
        req = urllib.request.Request(url, data=data, headers={"User-Agent": USER_AGENT, "Accept": accept,
                                                               **({"Content-Type": "application/json"} if data else {})})
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                body = resp.read()
            if host in _slow:  # recover speed gradually after a 429
                with _guard:
                    _slow[host] *= 0.85
                    if _slow[host] < 0.5:
                        _slow.pop(host, None)
            return body
        except urllib.error.HTTPError as e:
            last, status = e, e.code
            if e.code in (400, 401, 403, 404, 410, 422):
                break  # wrong board name or not allowed: retrying won't help
            if e.code == 429:  # too fast for this host: slow down for the rest of the run
                with _guard:
                    _slow[host] = min(max(_slow.get(host, 0.0) * 2, 2.0), 15.0)
                ra = (e.headers.get("Retry-After") if e.headers else None) or ""
                if attempt < retries:
                    time.sleep(min(float(ra), 30.0) if ra.strip().isdigit() else _slow[host])
                continue
        except (urllib.error.URLError, TimeoutError, ConnectionError, OSError) as e:
            last = e
        if attempt < retries:
            time.sleep(delay)
            delay *= 2
    raise FetchError(f"{url}: {last}", status)


def get_json(url: str, timeout: float = 20.0, retries: int = 2, min_interval: float | None = None):
    raw = get_bytes(url, timeout, retries, min_interval)
    try:
        return json.loads(raw.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as e:
        raise FetchError(f"{url}: not JSON ({e})")


def get_text(url: str, timeout: float = 20.0, retries: int = 2, min_interval: float | None = None) -> str:
    return get_bytes(url, timeout, retries, min_interval, accept="*/*").decode("utf-8", "replace")
