"""Polite JSON fetching: one request per host per second, bounded retries, backoff."""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from urllib.parse import urlparse

USER_AGENT = "careeros/0.1 (+https://github.com/VishStack01/careeros; job-search scout)"
_last: dict[str, float] = {}


class FetchError(RuntimeError):
    pass


def get_json(url: str, timeout: float = 20.0, retries: int = 2, min_interval: float = 1.0):
    host = urlparse(url).netloc
    wait = _last.get(host, 0) + min_interval - time.monotonic()
    if wait > 0:
        time.sleep(wait)
    delay = 1.5
    last_err: Exception | None = None
    for attempt in range(retries + 1):
        _last[host] = time.monotonic()
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            last_err = e
            if e.code in (404, 401, 403):
                break  # wrong board name or not allowed: retrying won't help
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as e:
            last_err = e
        if attempt < retries:
            time.sleep(delay)
            delay *= 2
    raise FetchError(f"{url}: {last_err}")
