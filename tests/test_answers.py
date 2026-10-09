import json
import tomllib
from pathlib import Path

from careeros.apply.answers import ESCALATE, HIGH, MEDIUM, SKIP, Context, Field, match_option, ready_to_submit, resolve

ROOT = Path(__file__).parents[1]
PROFILE = tomllib.loads((ROOT / "config" / "profile.example.toml").read_text())
BRAIN = json.loads((ROOT / "brain" / "brain.example.json").read_text())


def ctx(**kw):
    return Context(PROFILE, BRAIN, kw.get("package", {}), kw.get("job", {"location": "Bengaluru", "region": "south-india"}))


def r(label, type="text", required=True, options=None, **kw):
    return resolve(Field("k", label, type, required, options or []), ctx(**kw))


def test_identity_fields():
    assert r("First Name").value == "Asha"
    assert r("Email").value == "asha@example.com"
    assert r("LinkedIn Profile").value.endswith("asha-example")
    assert r("Current location").value == "Bengaluru, Karnataka, India"


def test_eeo_declines():
    res = r("Gender", "select", options=["Select...", "Male", "Female", "Decline to self-identify"])
    assert res.value == "Decline to self-identify" and res.confidence == HIGH


def test_yes_no_and_authorization():
    res = r("Will you now or in the future require visa sponsorship?", "radio", options=["Yes", "No"])
    assert res.value == "No"
    res = r("Are you legally authorized to work in the United States?", "radio", options=["Yes", "No"])
    assert res.value == "No"
    res = r("Are you legally authorized to work in India?", "radio", options=["Yes", "No"])
    assert res.value == "Yes"
    # No country named, role abroad: a human decides.
    res = r("Are you authorized to work in the country where this job is located?", "radio", options=["Yes", "No"],
            job={"location": "London", "region": "remote-global"})
    assert res.confidence == ESCALATE


def test_numeric_option_ranges():
    assert match_option(30, ["Immediately", "15 days or less", "16-30 days", "More than 30 days"])[0] == "16-30 days"
    assert r("Notice period", "select", options=["Immediate", "Up to 30 days", "31-60 days"]).value == "Up to 30 days"
    assert r("Years of experience with Python", "select", options=["Less than 1 year", "1-3 years", "3+ years"]).value == "1-3 years"


def test_skill_years_from_brain_is_medium():
    res = r("How many years of experience do you have with RAG?", "number")
    assert res.value == 1 and res.confidence == MEDIUM


def test_sensitive_fields_never_autofilled():
    for label in ("Aadhaar number", "Date of Birth", "PAN"):
        assert r(label).confidence == ESCALATE


def test_essays_escalate_unless_packaged():
    q = "Why do you want to work at Demo Co?"
    assert r(q, "textarea").confidence == ESCALATE
    pkg = {"answers": {"Why do you want to work at Demo Co?": "Because ..."}}
    assert r(q, "textarea", package=pkg).confidence == HIGH
    assert r("Why do you want to join Demo Co?", "textarea", package=pkg).confidence == MEDIUM


def test_optional_unknown_is_skipped():
    assert r("Favourite colour", required=False).confidence == SKIP


def test_privacy_ack_respects_policy():
    assert r("I acknowledge the privacy notice", "checkbox").confidence == ESCALATE


def test_ready_to_submit():
    c = ctx()
    fields = [Field("a", "First Name", required=True), Field("b", "Why us?", "textarea", True)]
    ok, reasons = ready_to_submit([resolve(f, c) for f in fields])
    assert not ok and "Why us?" in reasons[0]
