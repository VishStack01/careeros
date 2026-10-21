"""careeros doctor: is this install ready, and is your private data private?

Each check prints OK, WARN or FAIL with the fix. FAIL means something CareerOS
needs is missing; WARN means a feature is off or something deserves a look.
Nothing here touches the network unless you pass --online.
"""

from __future__ import annotations

import importlib.util
import os
import shutil
import subprocess
import sys
from pathlib import Path

PRIVATE = ["config/settings.toml", "config/profile.toml", "config/watchlist.toml", "brain/brain.json", "brain/evidence/",
           "packages/", "receipts/", "reports/", "jds/", "connections/", "data/", ".env"]


def _has(mod: str) -> bool:
    return importlib.util.find_spec(mod) is not None


def checks(root: Path, db_path: str, online: bool = False) -> list[tuple[str, str, str]]:
    """[(level, what, fix)]"""
    out: list[tuple[str, str, str]] = []
    add = lambda lvl, what, fix="": out.append((lvl, what, fix))

    v = sys.version_info
    add("OK" if v >= (3, 11) else "FAIL", f"Python {v.major}.{v.minor}", "" if v >= (3, 11) else "Install Python 3.11 or newer.")

    for name, fix in (("config/settings.toml", "Run `careeros init`, then edit it."), ("config/profile.toml", "Run `careeros init`, then fill in your details.")):
        add("OK" if (root / name).exists() else "WARN", name + (" found" if (root / name).exists() else " missing"), "" if (root / name).exists() else fix)

    bp = root / "brain" / "brain.json"
    if bp.exists():
        from . import brain
        try:
            problems = brain.validate(brain.load(bp))
            add("OK" if not problems else "WARN", f"Career Brain: {len(brain.claims(brain.load(bp)))} claims, {len(problems)} problem(s)",
                "" if not problems else "Run `careeros brain-check` to see them; claims without evidence can't reach a resume.")
        except ValueError as e:
            add("FAIL", "Career Brain isn't valid JSON", str(e)[:120])
    else:
        add("WARN", "No Career Brain yet", "Build it with the `career-brain` skill; tailoring and scoring need it.")

    if _has("playwright"):
        exe = os.environ.get("PLAYWRIGHT_BROWSERS_PATH") or str(Path.home() / ".cache" / "ms-playwright")
        found = Path(exe).exists() and any(Path(exe).glob("chromium*"))
        add("OK" if found else "WARN", "Playwright installed" + ("" if found else ", but no Chromium found"),
            "" if found else "Run `python -m playwright install chromium` (needed for `careeros apply` and `careeros render`).")
    else:
        add("WARN", "Playwright not installed", 'pip install "careeros[browser]" to fill forms and render PDFs.')
    add("OK" if _has("pypdf") or shutil.which("pdftotext") else "WARN", "PDF reader for the PDF fact check" + ("" if _has("pypdf") or shutil.which("pdftotext") else " missing"),
        "" if _has("pypdf") or shutil.which("pdftotext") else "pip install pypdf")

    try:
        from .store import Store
        st = Store(db_path)
        n = len(st.list("jobs"))
        paused = st.flag("paused")
        add("OK", f"Database {db_path}: {n} role(s)")
        add("WARN" if paused else "OK", "Submissions are paused" if paused else "Submissions are on (kill switch: `careeros pause`)",
            "Run `careeros resume` when you're ready." if paused else "")
    except Exception as e:  # noqa: BLE001 - report any storage problem as a finding
        add("FAIL", f"Database {db_path} can't be opened", str(e)[:160])

    if (root / ".git").exists() and shutil.which("git"):
        tracked = subprocess.run(["git", "-C", str(root), "ls-files", "--", *PRIVATE], capture_output=True, text=True).stdout.split()
        add("FAIL" if tracked else "OK", "Private files tracked by git: " + ", ".join(tracked[:6]) if tracked else "No private files are tracked by git",
            "Untrack them (`git rm --cached <file>`) and keep them out of any public repo." if tracked else "")
        gi = (root / ".gitignore").read_text(encoding="utf-8") if (root / ".gitignore").exists() else ""
        missing = [p for p in ("brain/brain.json", "data/", "packages/", "jds/") if p not in gi]
        if missing:
            add("WARN", ".gitignore doesn't list " + ", ".join(missing), "Add them so your data can't be committed by accident.")

    if os.environ.get("CAREEROS_DATABASE_URL") or os.environ.get("DATABASE_URL"):
        try:
            from .cloud.config import Config
            problems = Config.from_env().check()
            add("OK" if not problems else "FAIL", "Cloud configuration" + (" looks safe" if not problems else ": " + "; ".join(problems)[:200]),
                "" if not problems else "See docs/cloud.md.")
        except ImportError:
            add("WARN", "Cloud settings found but the cloud extras aren't installed", 'pip install "careeros[cloud]"')

    if online:
        import urllib.request
        for url, what in (("https://raw.githubusercontent.com", "GitHub (for the feed)"), ("https://boards-api.greenhouse.io/v1/boards/greenhouse/jobs", "a hiring-system API")):
            try:
                urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "careeros-doctor"}), timeout=10)
                add("OK", f"Can reach {what}")
            except OSError as e:
                code = getattr(e, "code", None)
                add("OK" if code and code < 500 else "WARN", f"Can reach {what}" if code and code < 500 else f"Can't reach {what}",
                    "" if code and code < 500 else "Check the network or proxy; scans and liveness checks need it.")
    return out


def run(root: Path, db_path: str, online: bool = False) -> int:
    res = checks(root, db_path, online)
    for lvl, what, fix in res:
        print(f"{lvl:<5} {what}" + (f"\n      {fix}" if fix else ""))
    fails = sum(1 for r in res if r[0] == "FAIL")
    warns = sum(1 for r in res if r[0] == "WARN")
    print(f"\n{fails} problem(s), {warns} warning(s)." if fails or warns else "\nAll good.")
    return 1 if fails else 0
