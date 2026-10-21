"""Which of the posting's terms your resume uses, and where.

    careeros keywords --jd jd.txt --resume packages/<id>/resume.json [--terms "Python,RAG,..."]

This is a coverage list, never an "ATS score": no one outside the company can
know how its screening software ranks a resume, and a number would invite
keyword stuffing. Each term is one of:

* present: in your summary or a bullet, so it is backed by a claim;
* thin:    only in your skills list (a recruiter skimming bullets won't see it);
* missing: nowhere. Add it only if the brain has a claim that uses it.
"""

from __future__ import annotations

import re
from collections import Counter

from .tags import SKILLS

EXTRA = [
    ("LLM agents", r"\bagent(s|ic)?\b"), ("Evals", r"\bevals?\b|\bevaluation (set|harness|framework)s?\b"),
    ("Prompt engineering", r"\bprompt(ing| engineering| design)\b"), ("Fine-tuning", r"\bfine[- ]?tun(e|ed|ing)\b"),
    ("Vector databases", r"\bvector (db|database|store|search)s?\b|\bpinecone|weaviate|qdrant|pgvector|chroma(db)?\b"),
    ("OpenAI API", r"\bopenai\b"), ("Anthropic API", r"\banthropic|claude api\b"), ("Hugging Face", r"\bhugging ?face\b"),
    ("LlamaIndex", r"\bllama ?index\b"), ("MLOps", r"\bmlops|llmops\b"), ("CI/CD", r"\bci/?cd\b|\bcontinuous (integration|delivery)\b"),
    ("REST APIs", r"\brest(ful)? apis?\b"), ("Microservices", r"\bmicro-?services?\b"), ("Airflow", r"\bairflow\b"), ("dbt", r"\bdbt\b"),
    ("Pandas", r"\bpandas\b"), ("NumPy", r"\bnumpy\b"), ("scikit-learn", r"\bscikit|sklearn\b"), ("Redis", r"\bredis\b"),
    ("MongoDB", r"\bmongo(db)?\b"), ("Git", r"\bgit\b(?!hub)"), ("Linux", r"\blinux\b"), ("Terraform", r"\bterraform\b"),
    ("n8n", r"\bn8n\b"), ("Zapier", r"\bzapier\b"), ("Make", r"\bmake\.com\b"), ("Tableau", r"\btableau\b"), ("Power BI", r"\bpower ?bi\b"),
    ("Machine learning", r"\bmachine learning\b|\bml\b"), ("NLP", r"\bnlp\b|natural language processing"), ("Computer vision", r"\bcomputer vision\b"),
    ("Data pipelines", r"\b(data|etl|elt) pipelines?\b"), ("System design", r"\bsystem design\b"), ("A/B testing", r"\ba/b test"),
    ("Product discovery", r"\bproduct discovery\b|\buser research\b"), ("Prototyping", r"\bprototyp(e|es|ing)\b"),
    ("Design systems", r"\bdesign systems?\b"), ("Stakeholder management", r"\bstakeholders?\b"),
]
VOCAB = list(SKILLS) + EXTRA


def _rx(term: str) -> str:
    for name, rx in VOCAB:
        if name.lower() == term.lower():
            return rx
    esc = re.escape(term.strip()).replace(r"\ ", r"[\s-]+")
    return rf"(?<![A-Za-z0-9]){esc}(?:s|es)?(?![A-Za-z0-9])"


def extract(jd: str, limit: int = 20) -> list[str]:
    """The posting's terms from the shared vocabulary, most mentioned first, then earliest."""
    hits = []
    for name, rx in VOCAB:
        found = list(re.finditer(rx, jd or "", re.I))
        if found:
            hits.append((-len(found), found[0].start(), name))
    return [n for *_, n in sorted(hits)][:limit]


def _resume_parts(resume: dict | str) -> tuple[str, str]:
    if isinstance(resume, str):
        return resume, ""
    body = " ".join([resume.get("headline", ""), resume.get("summary", "")] + [b.get("text", "") for b in resume.get("bullets", [])])
    return body, " ".join(resume.get("skills", []))


def coverage(terms: list[str], resume: dict | str) -> dict:
    body, skills = _resume_parts(resume)
    present, thin, missing = [], [], []
    for t in dict.fromkeys(x.strip() for x in terms if x and x.strip()):
        rx = _rx(t)
        if re.search(rx, body, re.I):
            present.append(t)
        elif re.search(rx, skills, re.I):
            thin.append(t)
        else:
            missing.append(t)
    n = len(present) + len(thin) + len(missing)
    return {"present": present, "thin": thin, "missing": missing,
            "summary": f"{len(present)} of {n} posting terms appear in your summary or bullets"
                       + (f", {len(thin)} only in your skills list" if thin else "") + "."}


def repeated(resume: dict) -> list[str]:
    """Terms used in more than half the bullets: likely stuffing."""
    bullets = [b.get("text", "") for b in resume.get("bullets", [])]
    if len(bullets) < 4:
        return []
    c = Counter()
    for b in bullets:
        for name, rx in VOCAB:
            if re.search(rx, b, re.I):
                c[name] += 1
    return [k for k, v in c.items() if v > len(bullets) / 2]
