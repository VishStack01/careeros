"""Scouts for public ATS job-board APIs.

These are the official, public, read-only JSON endpoints that Greenhouse,
Lever and Ashby publish for every company's career page. They are the most
reliable source of truth (the company's own posting, with real dates) and
the safest to poll. Job boards without public APIs (Wellfound, Internshala,
YC) are covered by the agent skill, not by this package.
"""

from __future__ import annotations

from . import ashby, greenhouse, lever
from .http import FetchError

SCOUTS = {"greenhouse": greenhouse.fetch, "lever": lever.fetch, "ashby": ashby.fetch}

__all__ = ["SCOUTS", "FetchError"]
