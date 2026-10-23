"""Tags for the job board: level, contract type, category and skills.

Everything is read from the title and the posting text with small, explicit
rules, so a tag can always be traced back to a word in the posting.
"""

from __future__ import annotations

import re

CATEGORIES = [
    ("AI & ML", r"\b(ai|a\.i\.|ml|machine learning|llm|genai|gen ai|generative|deep learning|nlp|computer vision|data scientist|applied scientist|prompt|agentic|agents?)\b"),
    ("Data", r"\b(data (engineer|analyst|platform)|analytics|analyst|bi developer|etl|power bi|snowflake|dbt)\b"),
    ("Backend", r"\b(backend|back[- ]end|server[- ]side|api engineer|platform engineer|distributed systems)\b"),
    ("Frontend", r"\b(frontend|front[- ]end|ui engineer|web developer|react developer)\b"),
    ("Full stack", r"\b(full[- ]?stack|fullstack)\b"),
    ("Mobile", r"\b(mobile|android|ios|react native|flutter|swift|kotlin)\b"),
    ("DevOps & Cloud", r"\b(devops|sre|site reliability|cloud|infrastructure|kubernetes|platform ops)\b"),
    ("Security", r"\b(security|appsec|iam|soc analyst|penetration)\b"),
    ("QA", r"\b(qa|quality assurance|test engineer|sdet|tester|automation tester)\b"),
    ("Design", r"\b(designer|design engineer|ux|ui/ux|product design)\b"),
    ("Product", r"\b(product manager|product owner|apm|program manager)\b"),
    ("Solutions & support", r"\b(solutions? engineer|forward deployed|customer engineer|support engineer|implementation|sales engineer|developer success)\b"),
    ("Research", r"\b(research (engineer|scientist)|researcher)\b"),
]

SKILLS = [
    ("Python", r"\bpython\b"), ("Java", r"\bjava\b(?!script)"), ("JavaScript", r"\bjavascript\b"), ("TypeScript", r"\btypescript\b"),
    ("React", r"\breact(\.js|js)?\b(?! native)"), ("Next.js", r"\bnext\.?js\b"), ("Node.js", r"\bnode(\.js|js)?\b"), ("Go", r"\b(golang|go \(golang\)|in go\b)"),
    ("Rust", r"\brust\b"), ("C++", r"c\+\+"), ("Kotlin", r"\bkotlin\b"), ("Swift", r"\bswift\b"), ("Flutter", r"\bflutter\b"),
    ("React Native", r"\breact native\b"), ("SQL", r"\bsql\b"), ("PostgreSQL", r"\bpostgres(ql)?\b"), ("AWS", r"\baws\b"),
    ("GCP", r"\b(gcp|google cloud)\b"), ("Azure", r"\bazure\b"), ("Kubernetes", r"\bkubernetes|k8s\b"), ("Docker", r"\bdocker\b"),
    ("PyTorch", r"\bpytorch\b"), ("TensorFlow", r"\btensorflow\b"), ("LLMs", r"\bllms?\b|large language model"), ("RAG", r"\brag\b|retrieval[- ]augmented"),
    ("LangChain", r"\blangchain|langgraph\b"), ("Figma", r"\bfigma\b"), ("Spark", r"\bspark\b"), ("Kafka", r"\bkafka\b"),
    ("Django", r"\bdjango\b"), ("FastAPI", r"\bfastapi\b"), ("Spring", r"\bspring( boot)?\b"), ("GraphQL", r"\bgraphql\b"),
]

_INTERN = re.compile(r"\bintern(ship)?\b|\btrainee\b|\bapprentice", re.I)
_CONTRACT = re.compile(r"\bcontract(or)?\b|\bfreelance\b|\bfixed[- ]term\b", re.I)
_PART = re.compile(r"\bpart[- ]time\b", re.I)
_VISA = re.compile(r"visa sponsorship (is )?(available|provided|offered)|we (can |will )?sponsor (your )?visa|relocation and visa", re.I)
_NO_VISA = re.compile(r"(no|not|unable to|cannot|can't|do not) (offer |provide )?(visa )?sponsor", re.I)
_RELOCATION = re.compile(r"relocation (support|assistance|package|bonus)", re.I)


def level(title: str, facts: dict) -> str:
    if _INTERN.search(title or ""):
        return "Internship"
    e = facts.get("expMin")
    if facts.get("senior") or (e is not None and e >= 5):
        return "Senior"
    if e is None:
        return "Fresher" if facts.get("fresherOk") else "Not stated"
    if e == 0:
        return "Fresher"
    if e <= 2:
        return "Entry"
    return "Mid"


def job_type(title: str, text: str) -> str:
    blob = f"{title}\n{text[:3000]}"
    if _INTERN.search(title or ""):
        return "Internship"
    if _PART.search(blob):
        return "Part-time"
    if _CONTRACT.search(title or "") or re.search(r"\b(employment type|job type)\W+(contract|freelance)", blob, re.I):
        return "Contract"
    return "Full-time"


def categories(title: str) -> list[str]:
    return [name for name, rx in CATEGORIES if re.search(rx, title or "", re.I)][:2]


def skills(title: str, text: str, limit: int = 6) -> list[str]:
    blob = f"{title}\n{text}"
    found = []
    for name, rx in SKILLS:
        m = re.search(rx, blob, re.I)
        if m:
            found.append((m.start(), name))
    return [n for _, n in sorted(found)][:limit]


def perks(text: str) -> list[str]:
    out = []
    if _VISA.search(text or "") and not _NO_VISA.search(text or ""):
        out.append("Visa sponsorship")
    if _RELOCATION.search(text or ""):
        out.append("Relocation")
    return out


def pay_tier(facts: dict) -> str:
    """From the pay the posting states (never estimated): "20+" (20 LPA or more at the top
    of the range), "10-20", "under-10", or "" when no pay is stated."""
    hi = facts.get("salaryHigh")
    if hi is None:
        return ""
    return "20+" if hi >= 20 else "10-20" if hi >= 10 else "under-10"


def tag(title: str, text: str, facts: dict) -> dict:
    from .signals import archetype  # signals imports this module
    return {"level": level(title, facts), "type": job_type(title, text), "categories": categories(title),
            "skills": skills(title, text), "perks": perks(text), "archetype": archetype(title, text), "payTier": pay_tier(facts)}
