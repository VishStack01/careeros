"""Company logos for the public job board.

A company gets its logo only when its own website can be named from evidence:

1. the website on record for the company (boards.json),
2. the company's own careers host (careers.airbnb.com, not an ATS or a job board),
3. a domain written in its postings (a link or an email address) whose name matches the company,
4. failing those, <name>.com, .in, .ai, .io or .co, used only when that site's own title names the company.

A guess is never used without that check, so a role doesn't show another company's logo. The icon is
fetched once per domain (the site's declared icon through Google's public favicon service, then the
site's own apple-touch-icon), saved next to the site and refreshed every 30 days. Companies without a
logo keep their initial.
"""

from __future__ import annotations

import gzip
import hashlib
import json
import re
import struct
import urllib.error
import urllib.request
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable, Iterable

UA = "Mozilla/5.0 (compatible; PropeloLogos/1.0; +https://propelo.in)"
REFRESH_DAYS = 30
RETRY_DAYS = 14

# Hosts that are never a company's own site: hiring systems, job boards, link shorteners and sharing sites.
NOT_COMPANY = re.compile(
    r"(^|\.)(greenhouse\.io|lever\.co|ashbyhq\.com|myworkdayjobs\.com|myworkdaysite\.com|workday\.com|smartrecruiters\.com|workable\.com|"
    r"recruitee\.com|teamtailor\.com|breezy\.hr|zohorecruit\.\w+|bamboohr\.com|jobvite\.com|icims\.com|personio\.\w+|rippling\.com|"
    r"keka\.com|darwinbox\.\w+|freshteam\.com|jazzhr\.com|applytojob\.com|pinpointhq\.com|dover\.com|gem\.com|polymer\.co|"
    r"ycombinator\.com|workatastartup\.com|himalayas\.app|jobicy\.com|weworkremotely\.com|remoteok\.com|remotive\.com|wellfound\.com|"
    r"angel\.co|linkedin\.com|lnkd\.in|glassdoor\.\w+|indeed\.\w+|naukri\.com|instahyre\.com|cutshort\.io|foundit\.in|monster\.\w+|"
    r"internshala\.com|unstop\.com|hirist\.\w+|iimjobs\.com|bit\.ly|goo\.gl|tinyurl\.com|forms\.gle|docs\.google\.com|youtu\.be|"
    r"w3\.org|schema\.org|gstatic\.com|googleapis\.com|cloudfront\.net|amazonaws\.com|herokuapp\.com|vercel\.app|netlify\.app)$", re.I)
SECOND_LEVEL = {"co.in", "net.in", "org.in", "firm.in", "gen.in", "ind.in", "co.uk", "org.uk", "com.au", "com.sg", "co.jp", "com.br",
                "co.nz", "co.za", "com.my", "com.ph", "co.id", "com.hk", "com.tw", "com.mx", "com.tr", "com.cn", "ac.in", "edu.in"}
_DOMAIN = re.compile(r"(?<![\w@.-])(?:https?://)?(?:[a-z0-9-]+\.)*([a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.(?:[a-z]{2,3}\.)?[a-z]{2,12})(?![\w-])", re.I)
_EMAIL = re.compile(r"[\w.+-]+@((?:[a-z0-9-]+\.)+[a-z]{2,12})", re.I)
_TLDS = {"com", "in", "io", "ai", "co", "org", "net", "dev", "app", "tech", "so", "xyz", "us", "uk", "de", "fr", "sg", "jp", "cloud", "health",
         "finance", "money", "gg", "me", "global", "world", "ly", "to", "sh", "is", "eu", "nl", "se", "ch", "ca", "au", "es", "it", "hq",
         "work", "jobs", "careers", "studio", "design", "games", "bio", "inc", "llc", "ltd", "team", "systems", "network", "digital", "store"}
_SUFFIX = {"pvt", "private", "ltd", "limited", "inc", "llc", "llp", "plc", "corp", "corporation", "co", "company", "gmbh", "sa", "ag", "bv",
           "sp", "z", "o", "oo", "the", "india", "technologies", "technology", "solutions", "services", "software", "labs", "lab", "group",
           "holdings", "global", "international", "systems", "ventures", "hq", "and"}


def registrable(host: str) -> str:
    """'careers.airbnb.com' -> 'airbnb.com', 'jobs.tcs.co.in' -> 'tcs.co.in'."""
    parts = [p for p in (host or "").lower().strip(".").split(".") if p]
    if len(parts) < 2:
        return ""
    if ".".join(parts[-2:]) in SECOND_LEVEL and len(parts) >= 3:
        return ".".join(parts[-3:])
    return ".".join(parts[-2:])


def _label(domain: str) -> str:
    return domain.split(".")[0]


def name_keys(company: str) -> set[str]:
    """The forms a company's own domain label can take: 'Sarvam AI' -> {'sarvamai', 'sarvam'}."""
    words = re.findall(r"[a-z0-9]+", (company or "").lower().replace("&", " and "))
    core = [w for w in words if w not in _SUFFIX] or words
    keys = {"".join(words), "".join(core), "-".join(core)}
    if core and len(core[0]) >= 4:
        keys.add(core[0])
    if len(core) >= 2:
        keys.add("".join(core[:2]))
    return {k for k in keys if len(k) >= 3}


def matches(company: str, domain: str) -> bool:
    label, keys = _label(domain).lower(), name_keys(company)
    if label in keys or label.replace("-", "") in keys:
        return True
    if any(label in (p + k, k + s) for k in keys for p in ("get", "try", "join", "use", "with", "go") for s in ("hq", "app", "ai", "labs", "inc", "io")):
        return True
    named = re.search(r"\b([a-z0-9-]+\.[a-z]{2,12})\b", (company or "").lower())  # 'Lingo.dev', 'Postman.com'
    return bool(named and registrable(named.group(1)) == domain)


def _host(url: str) -> str:
    m = re.match(r"^https?://([^/:?#]+)", url or "", re.I)
    return m.group(1).lower() if m else ""


def domains_in(text: str) -> list[str]:
    found = []
    for rx in (_EMAIL, _DOMAIN):
        for m in rx.finditer(text or ""):
            d = registrable(m.group(1).lower())
            if d and d.split(".")[-1] in _TLDS | {"in"} and not NOT_COMPANY.search(d):
                found.append(d)
    return found


def domain_for(company: str, urls: Iterable[str], texts: Iterable[str], website: str = "") -> str:
    """The company's own domain, or "" when the evidence doesn't name one."""
    if website:
        d = registrable(_host(website) or website.lower())
        if d and not NOT_COMPANY.search(d):
            return d
    hosts = Counter()
    for u in urls:
        h = _host(u)
        d = registrable(h)
        if d and not NOT_COMPANY.search(h) and (matches(company, d) or re.match(r"^(careers?|jobs|apply|work|join)\.", h)):
            hosts[d] += 1
    if hosts:
        return hosts.most_common(1)[0][0]
    seen = Counter(d for t in texts for d in domains_in(t[:20000]) if matches(company, d))
    return seen.most_common(1)[0][0] if seen else ""


def _slug(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", (s or "").lower()).strip("-")[:80]


def discover(records: list[dict], texts: dict[str, str], websites: dict[str, str] | None = None) -> dict[str, str]:
    """Company slug (as the board uses it) -> its own domain, for every company with evidence."""
    websites = websites or {}
    by_co: dict[str, list[dict]] = defaultdict(list)
    for r in records:
        by_co[r["company"]].append(r)
    out = {}
    for name, rs in by_co.items():
        d = domain_for(name, [r.get("url", "") for r in rs], [texts.get(r["id"], "") or r.get("summary", "") for r in rs[:12]], websites.get(name, ""))
        if d:
            out[_slug(name)] = d
        elif guesses(name):
            out[_slug(name)] = "?" + ",".join(guesses(name)) + "|" + name
    return out


def guesses(company: str) -> list[str]:
    """Domains to try for a company with no evidence, best first. Each must pass verify() before use."""
    words = [w for w in re.findall(r"[a-z0-9]+", (company or "").lower()) if w not in _SUFFIX]
    out = []
    if len(words) > 1 and words[-1] in ("ai", "hq", "app", "io") and len("".join(words[:-1])) >= 4:
        base = "".join(words[:-1])  # 'Sarvam AI' -> sarvam.ai, 'Acme HQ' -> acmehq.com and acme.com
        out += [f"{base}.{words[-1]}"] if words[-1] in ("ai", "io") else []
        out += [f"{base}.com"]
    full = "".join(words)
    if len(full) >= 4:
        out += [f"{full}.{tld}" for tld in ("com", "in", "ai", "io", "co")]
    return list(dict.fromkeys(out))[:7]


def verify(domain: str, company: str, get: Getter) -> bool:
    """Does the site at `domain` call itself `company` (in its <title> or og:site_name)?"""
    status, ctype, body = get(f"https://{domain}/")
    if status != 200 or not body:
        return False
    html = body[:300_000].decode("utf-8", "ignore")
    names = re.findall(r"<title[^>]*>(.*?)</title>", html, re.I | re.S)[:1]
    names += re.findall(r"""<meta[^>]+property=["']og:site_name["'][^>]+content=["']([^"']+)""", html, re.I)
    flat = re.sub(r"[^a-z0-9]+", "", " ".join(names).lower())
    key = domain.split(".")[0].replace("-", "")
    return len(key) >= 4 and key in flat


# ------------------------------------------------------------------ fetching
Getter = Callable[[str], tuple[int, str, bytes]]


def http_get(url: str, limit: int = 512 * 1024) -> tuple[int, str, bytes]:
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "image/*,text/html;q=0.8,*/*;q=0.5"})
    try:
        with urllib.request.urlopen(req, timeout=8) as r:
            return r.status, r.headers.get("content-type", ""), r.read(limit + 1)[:limit + 1]
    except urllib.error.HTTPError as e:
        return e.code, "", b""
    except Exception:  # noqa: BLE001 - offline, DNS, TLS, timeouts: no logo
        return 0, "", b""


def sniff(body: bytes) -> tuple[str, int]:
    """(extension, width in px or 0 when unknown) for an image body, ('', 0) when it isn't one."""
    if body[:8] == b"\x89PNG\r\n\x1a\n" and len(body) >= 24:
        return "png", struct.unpack(">I", body[16:20])[0]
    if body[:3] == b"\xff\xd8\xff":
        return "jpg", 0
    if body[:6] in (b"GIF87a", b"GIF89a"):
        return "gif", struct.unpack("<H", body[6:8])[0]
    if body[:4] == b"RIFF" and body[8:12] == b"WEBP":
        return "webp", 0
    if body[:4] == b"\x00\x00\x01\x00":
        return "ico", body[6] or 256
    head = body[:400].lstrip().lower()
    if head.startswith(b"<svg") or (head.startswith(b"<?xml") and b"<svg" in body[:2000]):
        return "svg", 0
    return "", 0


def fetch_icon(domain: str, get: Getter = http_get) -> tuple[bytes, str] | None:
    """The company's icon, at least 32 px wide when the size is known."""
    tries = [f"https://www.google.com/s2/favicons?domain={domain}&sz=128", f"https://{domain}/apple-touch-icon.png",
             f"https://www.{domain}/apple-touch-icon.png"]
    for url in tries:
        status, ctype, body = get(url)
        if status != 200 or not (60 <= len(body) <= 400_000):
            continue
        ext, width = sniff(body)
        if not ext or (width and width < 32):
            continue
        return body, ext
    return None


def _now() -> datetime:
    return datetime.now(timezone.utc)


def update(cache: str | Path, mapping: dict[str, str], get: Getter = http_get, workers: int = 16, limit: int = 3000,
           now: datetime | None = None, log=print) -> dict:
    """Fetch icons for the domains in `mapping` that are new, stale or due a retry. The cache folder holds
    files/<hash>.<ext>, manifest.json (domain -> file and date) and companies.json (slug -> domain)."""
    cache, now = Path(cache), now or _now()
    (cache / "files").mkdir(parents=True, exist_ok=True)
    mf = cache / "manifest.json"
    manifest = json.loads(mf.read_text()) if mf.exists() else {}

    def due(d):
        m = manifest.get(d)
        if not m:
            return True
        age = now - datetime.fromisoformat(m["at"])
        return age > timedelta(days=RETRY_DAYS if m.get("miss") else REFRESH_DAYS)
    # Resolve guesses first: a guessed domain is kept only when the site names the company.
    pending = sorted({v for v in mapping.values() if v.startswith("?") and due(v)})[:limit]

    def check(v):
        cands, name = v[1:].split("|", 1)
        hit = next((d for d in cands.split(",") if verify(d, name, get)), "")
        return v, ({"domain": hit, "at": now.isoformat()} if hit else {"miss": True, "at": now.isoformat()})
    with ThreadPoolExecutor(max_workers=workers) as ex:
        for v, entry in ex.map(check, pending):
            manifest[v] = entry
    resolved = {}
    for slug, v in mapping.items():
        d = (manifest.get(v) or {}).get("domain", "") if v.startswith("?") else v
        if d:
            resolved[slug] = d
    mapping = resolved
    todo = sorted({d for d in mapping.values() if due(d)})[:limit]

    def one(d):
        got = fetch_icon(d, get)
        if not got:
            return d, {"miss": True, "at": now.isoformat()}
        body, ext = got
        name = hashlib.sha1(d.encode()).hexdigest()[:16] + "." + ext
        (cache / "files" / name).write_bytes(body)
        return d, {"file": name, "at": now.isoformat()}
    with ThreadPoolExecutor(max_workers=workers) as ex:
        for d, entry in ex.map(one, todo):
            old = manifest.get(d) or {}
            if entry.get("miss") and old.get("file") and (cache / "files" / old["file"]).exists():
                entry = {**old, "at": now.isoformat()}  # keep the logo we had if a refresh fails
            manifest[d] = entry
    mf.write_text(json.dumps(manifest, indent=0, sort_keys=True))
    (cache / "companies.json").write_text(json.dumps(mapping, indent=0, sort_keys=True))
    got = sum(1 for d in set(mapping.values()) if (manifest.get(d) or {}).get("file"))
    log(f"Logos: {len(mapping)} companies with a known website ({len(pending)} guesses checked), {len(todo)} icons fetched, {got} with a logo")
    return {"companies": len(mapping), "checked": len(pending), "fetched": len(todo), "withLogo": got}


def for_site(cache: str | Path | None) -> dict[str, str]:
    """Company slug -> logo file name in the cache, for the companies that have one."""
    if not cache or not (Path(cache) / "manifest.json").exists():
        return {}
    cache = Path(cache)
    manifest = json.loads((cache / "manifest.json").read_text())
    companies = json.loads((cache / "companies.json").read_text()) if (cache / "companies.json").exists() else {}
    out = {}
    for slug, d in companies.items():
        f = (manifest.get(d) or {}).get("file")
        if f and (cache / "files" / f).exists():
            out[slug] = f
    return out


def run(feed_dir: str | Path, cache: str | Path, get: Getter = http_get, log=print, **kw) -> dict:
    feed_dir = Path(feed_dir)

    def jsonl(p):
        if not p.exists():
            return []
        with gzip.open(p, "rt", encoding="utf-8") as f:
            return [json.loads(line) for line in f if line.strip()]
    records = jsonl(feed_dir / "india.jsonl.gz")
    texts = {t["id"]: t.get("text", "") for t in jsonl(feed_dir / "full.jsonl.gz")}
    websites = {}
    if (feed_dir / "boards.json").exists():
        boards = json.loads((feed_dir / "boards.json").read_text()).get("companies", {})
        websites = {k: v.get("website", "") for k, v in boards.items() if v.get("website")}
    return update(cache, discover(records, texts, websites), get=get, log=log, **kw)
