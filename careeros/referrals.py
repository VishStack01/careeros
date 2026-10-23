"""Referral finder: who to ask for a referral at a company, and what to say.

    careeros referrals --company "Razorpay" --title "SDE 1" \
        [--connections Connections.csv] [--people people.json] [--applicant applicant.json] [--json]

A referral is the single biggest lift to being shortlisted, so for each role
CareerOS finds the people most likely to refer you, in this order:

1. people you already know there (your LinkedIn Connections.csv export);
2. alumni of your college working there, then engineers on a similar team,
   then engineering managers and recruiters, found by
   * LinkedIn people-search links you open in your own signed-in browser, and
   * public web search (site:linkedin.com/in), whose results the agent passes
     in as --people [{name, headline, url, location, degree}].

It ranks them, explains each pick, and drafts a short connection note and a
referral ask from your own profile. You send every message yourself: CareerOS
never signs in to LinkedIn, never scrapes it and never sends anything there.
"""

from __future__ import annotations

import re
from urllib.parse import quote, urlencode

from . import connections as conn
from .dedupe import company_key

NOTE_LIMIT = 300  # LinkedIn's limit for a connection-request note

_ENG = re.compile(r"\b(engineer|developer|sde|swe|programmer|scientist|ml|ai|backend|frontend|full[ -]?stack|devops|sre|platform|data)\b", re.I)
_MGR = re.compile(r"\b(engineering manager|em\b|head of engineering|tech lead|team lead|lead engineer|director of engineering|hiring manager)\b", re.I)
_RECRUIT = re.compile(r"\b(recruiter|talent acquisition|talent partner|sourcer|hiring|people partner|ta\b)", re.I)
_TOO_SENIOR = re.compile(r"\b(vp|vice president|chief|cto|ceo|cfo|founder|co-founder|partner|president)\b", re.I)


def _college_words(college: str) -> list[str]:
    key = re.sub(r"\b(university|institute|of|technology|college|engineering|the|and|deemed|to|be)\b", " ", (college or "").lower())
    return [w for w in re.findall(r"[a-z]{3,}", key)][:2]


def search_links(company: str, title: str, applicant: dict | None = None) -> list[dict]:
    """People-search links to open in your own browser, most useful first."""
    a = applicant or {}
    college = " ".join(_college_words(a.get("college", ""))) or ""
    city = a.get("city", "")
    role = "software engineer" if not re.search(r"\b(ml|machine learning|ai|data)\b", title or "", re.I) else "machine learning engineer"
    li = "https://www.linkedin.com/search/results/people/?"
    out = []
    if college:
        out.append({"label": f"{college.title()} alumni at {company}", "url": li + urlencode({"keywords": f'"{company}" {college}', "origin": "GLOBAL_SEARCH_HEADER"})})
    out += [
        {"label": f"Engineers at {company}" + (f" in {city}" if city else ""), "url": li + urlencode({"keywords": f'"{company}" {role} {city}'.strip(), "origin": "GLOBAL_SEARCH_HEADER"})},
        {"label": f"2nd-degree connections at {company}", "url": li + urlencode({"keywords": f'"{company}"', "network": '["S"]', "origin": "FACETED_SEARCH"})},
        {"label": f"Engineering managers at {company}", "url": li + urlencode({"keywords": f'"{company}" engineering manager', "origin": "GLOBAL_SEARCH_HEADER"})},
        {"label": f"Recruiters at {company}", "url": li + urlencode({"keywords": f'"{company}" technical recruiter India', "origin": "GLOBAL_SEARCH_HEADER"})},
    ]
    g = "https://www.google.com/search?q="
    xr = f'site:linkedin.com/in "{company}" ("software engineer" OR "SDE" OR "developer")' + (f' "{college}"' if college else "")
    out.append({"label": "Web search for public profiles", "url": g + quote(xr)})
    return out


def score(person: dict, company: str, title: str, applicant: dict | None = None) -> tuple[int, list[str]]:
    """How likely this person is to refer you for this role, with the reasons."""
    a = applicant or {}
    head = " ".join(str(person.get(k) or "") for k in ("headline", "position", "title"))
    where = f"{person.get('company') or ''} {head}"
    s, why = 0, []
    tier = conn.tier(company, person.get("company") or "") if person.get("company") else ""
    if tier in ("exact", "strong") or (not person.get("company") and company_key(company) and company_key(company) in company_key(where)):
        if not tier and re.search(r"\b(ex[- ]?|former(ly)?\s+(at\s+)?|previously\s+(at\s+)?)@?\s*" + re.escape(company.split()[0]), head, re.I):
            return 0, ["Used to work there"]
        s += 40
        why.append(f"Works at {company}")
    else:
        return 0, ["Doesn't appear to work there now"]
    degree = str(person.get("degree") or ("1st" if person.get("connectedOn") else "")).lower()
    if degree.startswith("1"):
        s += 30
        why.append("Already a connection")
    elif degree.startswith("2"):
        s += 10
        why.append("2nd-degree: you share a connection")
    words = _college_words(a.get("college", ""))
    text = f"{head} {person.get('education') or ''}".lower()
    if words and all(w in text for w in words):
        s += 25
        why.append(f"Alumni of {a.get('college')}")
    if _MGR.search(head):
        s += 15
        why.append("Engineering manager or lead: can refer and often hires")
    elif _ENG.search(head):
        s += 20 if _ENG.search(title or "") else 10
        why.append("Engineer, likely on a similar team")
    elif _RECRUIT.search(head):
        s += 12
        why.append("Recruiter: can move your application to a hiring manager")
    if _TOO_SENIOR.search(head):
        s -= 15
        why.append("Very senior; less likely to reply")
    city = (a.get("city") or "").lower()
    if city and city[:5] in f"{person.get('location') or ''} {head}".lower():
        s += 5
        why.append(f"Also in {a.get('city')}")
    return max(s, 0), why


def rank(company: str, title: str, applicant: dict | None = None, connections: list[dict] | None = None,
         people: list[dict] | None = None, limit: int = 8) -> list[dict]:
    pool: dict[str, dict] = {}
    for r in conn.matches(company, connections or [], limit=50):
        pool[(r.get("url") or r["name"]).lower()] = dict(r, headline=r.get("position", ""), degree="1st", via="Your connections")
    for p in people or []:
        if not p.get("name"):
            continue
        key = (p.get("url") or p["name"]).lower()
        pool.setdefault(key, dict(p, via=p.get("via") or "Public web search"))
    out = []
    for p in pool.values():
        sc, why = score(p, company, title, applicant)
        if sc > 0:
            out.append({"name": p["name"], "headline": p.get("headline") or p.get("position", ""), "url": p.get("url", ""),
                        "via": p["via"], "score": sc, "why": why})
    out.sort(key=lambda x: -x["score"])
    return out[:limit]


def drafts(company: str, title: str, applicant: dict | None = None, person: dict | None = None, job_url: str = "") -> dict:
    """A connection note (300 characters at most) and a referral ask, from facts in the profile only."""
    a = applicant or {}
    me = (a.get("fullName") or "").split(" ")[0] or "I"
    them = ((person or {}).get("name") or "").split(" ")[0] or "there"
    now = " ".join(x for x in (a.get("currentTitle"), f"at {a['currentCompany']}" if a.get("currentCompany") else "") if x)
    school = a.get("college", "")
    alum = person and any("Alumni" in w for w in person.get("why", []))
    hook = f"Fellow {school} grad here. " if alum and school else ""
    note = (f"Hi {them}, {hook}I'm {me}, {now + ', ' if now else ''}applying for the {title} role at {company}. "
            f"Would you be open to a quick chat about the team, or referring me if I seem a fit? Thanks!")
    if len(note) > NOTE_LIMIT:
        note = f"Hi {them}, {hook}I'm {me}, applying for {title} at {company}. Open to a quick chat or a referral if I fit? Thanks!"
    note = note[:NOTE_LIMIT]
    ask = (f"Hi {them},\n\nThanks for connecting. I'm applying for the {title} role at {company}"
           + (f" ({job_url})" if job_url else "") + ". "
           + (f"I'm currently {now}" + (f" and studied at {school}" if school else "") + ". " if now else "")
           + "I've attached my resume. If you think I'd be a fit, would you be willing to refer me? "
           "If not, any advice on the team or the process would help a lot.\n\nThank you,\n" + (a.get("fullName") or ""))
    return {"connectionNote": note, "referralAsk": ask.strip()}


def plan(company: str, title: str, applicant: dict | None = None, connections: list[dict] | None = None,
         people: list[dict] | None = None, job_url: str = "") -> dict:
    ranked = rank(company, title, applicant, connections, people)
    return {"company": company, "title": title, "people": ranked, "searchLinks": search_links(company, title, applicant),
            "drafts": drafts(company, title, applicant, ranked[0] if ranked else None, job_url)}
