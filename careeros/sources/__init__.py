"""Scouts for public ATS job-board feeds.

These are the official, public, read-only feeds that hiring systems publish for
every company's career page. They are the most reliable source of truth (the
company's own posting, with real dates) and the safest to poll. Job boards
without public feeds (Wellfound, Internshala, YC and others) are covered by the
agent skill, not by this package.
"""

from __future__ import annotations

from . import amazon, ashby, breezy, greenhouse, lever, personio, recruitee, smartrecruiters, workable, workday
from .http import FetchError

SCOUTS = {
    "greenhouse": greenhouse.fetch,
    "lever": lever.fetch,
    "ashby": ashby.fetch,
    "workable": workable.fetch,
    "smartrecruiters": smartrecruiters.fetch,
    "recruitee": recruitee.fetch,
    "breezy": breezy.fetch,
    "personio": personio.fetch,
    "workday": workday.fetch,
    "amazon": amazon.fetch,
}

__all__ = ["SCOUTS", "FetchError"]
