"""Archive a posting's full text, verbatim, before applying.

    careeros archive-jd <url> [--job-id ID] [--out jds/]

Postings disappear, usually somewhere between applying and the second
interview, and with them the exact requirements you were assessed against. The
archive is the posting's text as published: read from the hiring system's API
when the URL is a Greenhouse, Lever, Ashby, SmartRecruiters or Workable posting,
otherwise from the page. Never summarised. The first line records the posted
date as the source shows it, never the date you saved it.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from .liveness import ats_api
from .sources.http import FetchError, get_json, get_text
from .textutil import html_to_text


def _from_api(kind: str, data: dict, jid: str = "") -> dict | None:
    if kind == "ashby":
        item = next((j for j in (data or {}).get("jobs", []) if str(j.get("id")) == jid), None)
        if not item:
            return None
        return {"title": item.get("title", ""), "text": item.get("descriptionPlain") or html_to_text(item.get("descriptionHtml", "")),
                "postedAt": item.get("publishedAt", "")}
    if kind == "greenhouse":
        return {"title": data.get("title", ""), "text": html_to_text(data.get("content", "")), "postedAt": data.get("updated_at", "")}
    if kind == "lever":
        parts = [data.get("descriptionPlain") or html_to_text(data.get("description", ""))]
        for block in data.get("lists", []) or []:
            parts.append(block.get("text", ""))
            parts.append(html_to_text(block.get("content", "")))
        parts.append(data.get("additionalPlain") or html_to_text(data.get("additional", "")))
        created = data.get("createdAt")
        posted = datetime.fromtimestamp(created / 1000, timezone.utc).strftime("%Y-%m-%d") if isinstance(created, (int, float)) else ""
        return {"title": data.get("text", ""), "text": "\n".join(p for p in parts if p), "postedAt": posted}
    if kind == "smartrecruiters":
        secs = ((data.get("jobAd") or {}).get("sections") or {})
        parts = []
        for key in ("companyDescription", "jobDescription", "qualifications", "additionalInformation"):
            s = secs.get(key) or {}
            if s.get("text"):
                parts += [s.get("title", ""), html_to_text(s["text"])]
        return {"title": data.get("name", ""), "text": "\n".join(p for p in parts if p), "postedAt": data.get("releasedDate", "")}
    if kind == "workable":
        text = "\n".join(html_to_text(data.get(k, "")) for k in ("description", "requirements", "benefits") if data.get(k))
        return {"title": data.get("title", ""), "text": text, "postedAt": data.get("published") or data.get("published_on", "")}
    return None


def fetch(url: str, fetch_json: Callable = get_json, fetch_text: Callable = get_text) -> dict:
    """{"title", "text", "postedAt", "via", "url"}. Raises FetchError when nothing could be read."""
    api = ats_api(url)
    if api:
        kind, endpoint = api
        try:
            if kind == "ashby":
                board, jid = endpoint.split("#")
                got = _from_api(kind, fetch_json(board), jid)
            else:
                got = _from_api(kind, fetch_json(endpoint))
            if got and len(got["text"]) > 200:
                return dict(got, via=f"{kind} api", url=url)
        except FetchError:
            pass
    html = fetch_text(url)
    title = re.search(r"<title[^>]*>(.*?)</title>", html, re.I | re.S)
    body = re.sub(r"<(script|style|nav|header|footer|noscript)[\s\S]*?</\1>", " ", html, flags=re.I)
    main = re.search(r"<main[\s\S]*?</main>", body, re.I)
    text = html_to_text(main.group(0) if main else body)
    posted = re.search(r'"datePosted"\s*:\s*"([^"]+)"', html)
    return {"title": html_to_text(title.group(1)) if title else "", "text": text, "postedAt": posted.group(1) if posted else "", "via": "page", "url": url}


def slug(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", (s or "").lower()).strip("-")[:60] or "posting"


def to_markdown(got: dict, company: str = "", now: datetime | None = None) -> str:
    now = now or datetime.now(timezone.utc)
    head = f"# {got.get('title') or 'Posting'}{' at ' + company if company else ''}\n\n"
    meta = (f"Posted: {got.get('postedAt') or 'not visible in source'}\n"
            f"URL: {got.get('url', '')}\nArchived: {now.strftime('%Y-%m-%d %H:%M UTC')} (via {got.get('via', 'page')})\n\n")
    return head + meta + "## Job description (archived verbatim)\n\n" + got.get("text", "").strip() + "\n"


def save(got: dict, out_dir: str | Path, company: str = "", name: str = "") -> Path:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    p = out / f"{name or slug(company + '-' + got.get('title', ''))}.md"
    p.write_text(to_markdown(got, company), encoding="utf-8")
    return p
