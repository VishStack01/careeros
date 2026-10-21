"""Pay, side by side: what the posting advertised, what you asked for, what you
said in each round, your floor, and the offer.

    careeros salary-gap --job-id ID
    careeros salary-gap --advertised "₹18-24 LPA" --ask 22 --floor 10 --offer "₹19 LPA fixed"

Facts only, in lakhs per annum. It never says whether to accept; it shows where
the offer sits so the negotiation brief (the `coach` skill) starts from numbers,
not impressions. Amounts in another currency are converted at a stated rate and
labelled so you can check them.
"""

from __future__ import annotations

import re

from .extract import parse_salary

_SHARED_UNIT = re.compile(r"(\d+(?:\.\d+)?)\s*(-|–|to)\s*(\d+(?:\.\d+)?)\s*([kKmM])\b")


def _lpa(x) -> tuple[float, float] | None:
    if x in (None, ""):
        return None
    if isinstance(x, (int, float)):
        return float(x), float(x)
    s = parse_salary(_SHARED_UNIT.sub(r"\1\4\2\3\4", str(x)))  # "$30-40K" means $30K-$40K
    if s is None:
        try:
            v = float(str(x).replace(",", "").strip())
            return v, v
        except ValueError:
            return None
    return s.low_lpa, s.high_lpa


def _f(v: float) -> str:
    return f"{v:.1f}".rstrip("0").rstrip(".")


def _show(r: tuple[float, float]) -> str:
    return f"{_f(r[0])} LPA" if r[0] == r[1] else f"{_f(r[0])}–{_f(r[1])} LPA"


def compare(advertised=None, ask=None, floor=None, offer=None, stated: list[dict] | None = None) -> dict:
    """{"rows": [...], "findings": [...], "consistent": bool}. `stated` is [{round, amount}] you told interviewers."""
    adv, a, fl, of = _lpa(advertised), _lpa(ask), _lpa(floor), _lpa(offer)
    rows = []
    for label, r in (("Posting advertised", adv), ("Your floor", fl), ("Your ask", a), ("Offer", of)):
        if r:
            rows.append({"what": label, "lpa": _show(r)})
    out: list[str] = []
    if of:
        o = of[1]
        if adv:
            if o < adv[0]:
                out.append(f"The offer ({_f(o)} LPA) is {_f(adv[0] - o)} LPA under the posting's own lower bound ({_f(adv[0])} LPA).")
            elif o >= adv[1]:
                out.append(f"The offer is at or above the top of the advertised range ({_f(adv[1])} LPA).")
            else:
                pos = (o - adv[0]) / (adv[1] - adv[0]) if adv[1] > adv[0] else 1
                out.append(f"The offer sits {pos:.0%} of the way up the advertised range ({_show(adv)}).")
        if a:
            gap = a[0] - o
            out.append(f"It is {_f(gap)} LPA under your ask ({_f(a[0])} LPA)." if gap > 0 else f"It meets your ask ({_f(a[0])} LPA).")
        if fl and o < fl[0]:
            out.append(f"It is under your floor ({_f(fl[0])} LPA).")
    elif adv and a and a[0] > adv[1]:
        out.append(f"Your ask ({_f(a[0])} LPA) is above the advertised range ({_show(adv)}); expect pushback, or a different level.")
    if any(re.search(r"\$|usd", str(v), re.I) for v in (advertised, ask, floor, offer)):
        out.append("Dollar amounts are converted at ₹88 per $1 a year; check today's rate.")
    said = [(s.get("round", "a round"), _lpa(s.get("amount"))) for s in stated or [] if _lpa(s.get("amount"))]
    distinct = {round(r[0], 1) for _, r in said}
    consistent = len(distinct) <= 1
    if not consistent:
        out.append("You've named different numbers in different rounds: " + "; ".join(f"{rd}: {_show(r)}" for rd, r in said)
                   + ". Settle on one before the next conversation.")
    return {"rows": rows, "findings": out, "consistent": consistent}


def for_job(job: dict, settings: dict | None = None, applicant: dict | None = None) -> dict:
    """compare() from a dashboard job and the user's settings and applicant details."""
    ev = job.get("evaluation") or {}
    adv = (ev.get("comp") or {}).get("advertised") or job.get("salary")
    offer = (job.get("offer") or {}).get("ctc") or (job.get("offer") or {}).get("text")
    return compare(advertised=adv, ask=(applicant or {}).get("expectedCtcLpa"), floor=(settings or {}).get("salaryFloorLpa"),
                   offer=offer, stated=job.get("salaryStated"))
