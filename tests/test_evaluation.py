"""Scored evaluations: validation rules, confidence, verdict bands, the apply line and the report."""

import copy
import json
import subprocess
import sys
from pathlib import Path

import pytest

from careeros import evaluation as E

ROOT = Path(__file__).resolve().parents[1]
EV = json.loads((ROOT / "examples" / "evaluation.example.json").read_text(encoding="utf-8"))
JD = (ROOT / "examples" / "jd.example.txt").read_text(encoding="utf-8")
BRAIN = json.loads((ROOT / "brain" / "brain.example.json").read_text(encoding="utf-8"))


def ev(**changes):
    e = copy.deepcopy(EV)
    e.update(changes)
    return e


def test_example_is_valid():
    errors, warnings = E.validate(EV, jd=JD, brain=BRAIN)
    assert errors == [] and warnings == []
    n = E.normalize(EV)
    assert n["verdict"]["band"] == "apply" and n["verdict"]["call"] == "Apply" and n["confidence"] == "medium"
    assert [r["match"] for r in n["requirements"][:2]] == ["strong", "strong"] and n["requirements"][2]["importance"] == "high"


@pytest.mark.parametrize("score,band,letter,fit", [(4.7, "strong", "A", "strong"), (4.0, "apply", "A", "good"),
                                                    (3.9, "consider", "B", "stretch"), (3.4, "skip", "F", "weak")])
def test_bands(score, band, letter, fit):
    b = E.band(score)
    assert (b["band"], b["decision"], b["fitBand"]) == (band, letter, fit)


def test_confidence_rules():
    assert E.confidence(EV) == "medium"
    high = ev(confidenceGaps=[])
    for d in high["dimensions"].values():
        d["status"] = "supported"
    assert E.confidence(high) == "high"
    low = copy.deepcopy(high)
    low["dimensions"]["cvMatch"]["status"] = "unknown"
    assert E.confidence(low) == "low"
    two = copy.deepcopy(high)
    two["dimensions"]["comp"]["status"] = two["dimensions"]["culture"]["status"] = "unknown"
    assert E.confidence(two) == "low"
    assert E.confidence(ev(flags={"eligibilityUnresolved": True})) == "low"
    errs, _ = E.validate(ev(confidence="high"))
    assert any("computed" in e for e in errs)


def test_score_rules():
    assert any("one decimal" in e for e in E.validate(ev(score=4.25))[0])
    assert any("outside its dimension" in e for e in E.validate(ev(score=2.0))[0])
    assert any("Decision A" in e for e in E.validate(ev(score=3.8, decision="A"))[0])
    _, warns = E.validate(ev(score=3.8))
    assert any("apply line" in w for w in warns)  # it still has draft answers


def test_requirement_rules():
    e = ev()
    e["requirements"][0]["jdSignal"] = "Must have 3+ years of Python."
    assert any("isn't a verbatim quote" in x for x in E.validate(e, jd=JD)[0])
    e = ev()
    e["requirements"][3].update(importance="high", tier="inferred")
    errs = E.validate(e)[0]
    assert any("inferred requirement can't be high" in x for x in errs)
    e = ev()
    e["requirements"][0]["claimId"] = "proj-voice"  # planned work
    assert any("planned work" in x for x in E.validate(e, brain=BRAIN)[0])
    e["requirements"][0]["claimId"] = "nope"
    assert any("isn't in the brain" in x for x in E.validate(e, brain=BRAIN)[0])
    e = ev(gaps=[])
    assert any("add a gap" in x for x in E.validate(e)[0])
    e = ev()
    e["requirements"] += [{"requirement": f"Extra {i}", "importance": "preferred", "tier": "structural", "match": "missing"} for i in range(10)]
    assert any("keep at most 12" in x for x in E.validate(e)[0])


def test_quotes_forgive_typography_not_words():
    assert E.verbatim("must have 1+ years of python in production", JD)
    assert E.verbatim("Build and ship LLM agents ... support tickets", JD)
    assert not E.verbatim("must have 2+ years of python", JD)
    assert E.verbatim("₹18–24 LPA", JD)  # en dash in the quote, hyphen in the posting


def test_company_and_comp_rules():
    assert any("low pay reliability" in x for x in E.validate(ev(company={"type": "Unknown", "compReliability": "medium"}))[0])
    assert any("company.type" in x for x in E.validate(ev(company={"type": "Unicorn", "compReliability": "high"}))[0])
    assert any("verbatim" in x for x in E.validate(ev(comp={"advertised": "₹30 LPA"}), jd=JD)[0])


def test_job_patch_and_apply_gate():
    n = E.normalize(EV)
    patch = E.job_patch(n)
    assert patch["decision"] == "A" and patch["fitBand"] == "good" and patch["score"] == 4.2
    assert patch["evidence"][0]["requirement"] and patch["gaps"][0].startswith("Evaluation sets")
    low = E.normalize(ev(score=3.6, answers=[]))
    assert E.job_patch(low, decision="A")["decision"] == "B"  # A is never below the line
    assert E.apply_gate({"evaluation": n}, chosen_by_user=False) == (True, "")
    ok, why = E.apply_gate({"evaluation": low}, chosen_by_user=True)
    assert not ok and "3.6" in why
    assert E.apply_gate({"evaluation": low, "scoreOverride": True}, chosen_by_user=True)[0]
    assert E.apply_gate({}, chosen_by_user=True)[0] and not E.apply_gate({}, chosen_by_user=False)[0]


def test_report():
    job = {"title": "AI Engineer (Agents)", "company": "Acme", "url": "https://acme.example/jobs/1", "location": "Remote, India",
           "legitimacy": {"tier": "high", "label": "Looks real", "signals": [{"signal": "Age", "status": "good", "note": "Posted 2 days ago."}]}}
    md = E.report_md(E.normalize(EV), job, JD)
    assert md.startswith("# AI Engineer (Agents) at Acme")
    assert "**Apply.**" in md and "## B) Match with your experience" in md and "## Score evidence" in md
    assert "## Job description (archived verbatim)" in md and "Must have 1+ years" in md
    assert "✅ Looks real" in md and "Interview risk:" in md


def test_cli_eval_check(tmp_path):
    out = tmp_path / "r.md"
    r = subprocess.run([sys.executable, "-m", "careeros", "eval-check", str(ROOT / "examples" / "evaluation.example.json"),
                        "--jd", str(ROOT / "examples" / "jd.example.txt"), "--brain", str(ROOT / "brain" / "brain.example.json"), "--md", str(out)],
                       capture_output=True, text=True, cwd=tmp_path)
    assert r.returncode == 0, r.stdout + r.stderr
    assert "Score 4.2/5" in r.stdout and out.exists()
    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps(ev(score=9)), encoding="utf-8")
    r = subprocess.run([sys.executable, "-m", "careeros", "eval-check", str(bad), "--brain", ""], capture_output=True, text=True, cwd=tmp_path)
    assert r.returncode != 0 and "ERROR" in r.stdout
