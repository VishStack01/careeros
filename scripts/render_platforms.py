"""Regenerate docs/platforms.md from config/platforms.toml.

    python scripts/render_platforms.py
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from careeros import platforms  # noqa: E402

GROUPS = [
    ("remote-board", "Remote job boards"),
    ("community", "Communities"),
    ("aggregator", "Aggregators that index company pages"),
    ("vc-portfolio", "VC portfolio job boards"),
    ("india-board", "Indian startup boards"),
    ("fresher", "Fresher-first"),
    ("talent-marketplace", "Talent marketplaces"),
    ("ai-contract", "AI work marketplaces"),
    ("xray", "X-ray searches"),
    ("big-board", "Big boards (email alerts only)"),
    ("company-list", "Company lists"),
]
ACCESS = {"feed": "Scanned (public feed)", "fetch": "Agent reads it", "login": "You apply (login)", "alerts": "Email alerts", "planned": "Planned (needs a free API key)"}


def link(p: dict) -> str:
    url = p["url"]
    if url.startswith("search:"):
        return f"`{url[7:]}`"
    return f"[{url.split('//', 1)[-1].rstrip('/')}]({url})"


def main() -> None:
    ps = platforms.load()
    s = platforms.summary(ps)
    out = [
        "# Job platforms",
        "",
        "Generated from [`config/platforms.toml`](../config/platforms.toml) by `scripts/render_platforms.py`. Edit the TOML, not this page.",
        "",
        f"**{s['total']} platforms**, {s['lowCompetition']} of them low-competition. "
        f"{s['byAccess'].get('feed', 0)} have public feeds and are scanned automatically every 3 hours; "
        f"{s['byAccess'].get('fetch', 0)} are read by the agent in rotation (every-run ones each time, the rest every third run); "
        f"{s['byAccess'].get('login', 0)} need your login, so the agent finds and prepares and you submit; "
        f"{s['byAccess'].get('alerts', 0)} big boards are covered by their own email alerts only.",
        "",
        "Why not 300-500? Past about a hundred, \"job sites\" are mostly clones and scrapers re-posting the same "
        "listings (often stale), or sites that only show jobs after login. They add duplicates, not openings. "
        "The real reach is the ~1,000 company career pages in [`config/companies/`](../config/companies/), "
        "read straight from each company's hiring system.",
        "",
        "`verify = true` marks URL patterns not yet confirmed; the first agent run checks them and reports any that moved.",
        "",
    ]
    for kind, title in GROUPS:
        rows = [p for p in ps if p.get("kind") == kind]
        if not rows:
            continue
        out += [f"## {title} ({len(rows)})", "", "| Platform | Region | Competition | How | Notes |", "|---|---|---|---|---|"]
        for p in rows:
            flags = (" · every run" if p.get("every_run") else "") + (" · to verify" if p.get("verify") else "")
            notes = (p.get("notes", "") or "").replace("|", "/")
            out.append(f"| {p['name']}<br>{link(p)} | {p['region']} | {p['competition']} | {ACCESS[p['access']]}{flags} | {notes} |")
        out.append("")
    (ROOT / "docs" / "platforms.md").write_text("\n".join(out), encoding="utf-8")
    print(f"Wrote docs/platforms.md ({s['total']} platforms)")


if __name__ == "__main__":
    main()
