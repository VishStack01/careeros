import json
from pathlib import Path

from careeros import brain, claims

BRAIN = json.loads((Path(__file__).parents[1] / "brain" / "brain.example.json").read_text())


def test_example_brain_is_valid():
    assert brain.validate(BRAIN) == []


def test_brain_flags_claims_without_proof():
    b = json.loads(json.dumps(BRAIN))
    b["projects"][0]["evidence"] = []
    assert any("no evidence" in p for p in brain.validate(b))


def test_truthful_resume_passes():
    resume = {
        "skills": ["Python", "RAG", "n8n"],
        "bullets": [
            {"text": "Automated entry of 600 invoices a month with n8n and an LLM, cutting manual work from 30 to 4 hours.", "refs": ["ach-invoices"]},
            {"text": "Shipped a RAG assistant over a 2,000-page wiki; 87% accuracy on 120 real questions.", "refs": ["ach-rag"]},
            {"text": "Built TicketRouter, an open-source LLM router handling 1,500 tickets a week at 94% tag accuracy.", "refs": ["proj-triage"]},
        ],
    }
    rep = claims.check(resume, BRAIN)
    assert rep.ok, rep.blocking
    assert rep.metric_density == 1.0


def test_invented_number_is_blocked():
    resume = {"bullets": [{"text": "Cut manual work by 95% across 600 invoices.", "refs": ["ach-invoices"]}]}
    rep = claims.check(resume, BRAIN)
    assert not rep.ok and "95" in rep.blocking[0]


def test_unreferenced_and_planned_work_blocked():
    rep = claims.check({"bullets": [{"text": "Led a team of 5.", "refs": []}]}, BRAIN)
    assert not rep.ok
    rep = claims.check({"bullets": [{"text": "Shipped a voice agent for clinics.", "refs": ["proj-voice"]}]}, BRAIN)
    assert any("planned work" in b for b in rep.blocking)


def test_tool_not_in_claim_blocked_and_unknown_skill_blocked():
    rep = claims.check({"bullets": [{"text": "Built an n8n flow for wiki search.", "refs": ["ach-rag"]}], "skills": ["Kubernetes"]}, BRAIN)
    assert any("n8n" in b for b in rep.blocking)
    assert any("Kubernetes" in b for b in rep.blocking)


def test_voice_warnings():
    rep = claims.check({"bullets": [{"text": "Leveraged n8n to automate 600 invoices a month.", "refs": ["ach-invoices"]}]}, BRAIN)
    assert rep.ok and any("leverage" in w.lower() for w in rep.warnings)
