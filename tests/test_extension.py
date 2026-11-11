"""The CareerOS Autofill extension: what it fills, what it leaves for you, and where it never runs.

The fill script runs against fixture forms in a real Chromium (skipped when Playwright or its
browser isn't installed). The manifest checks run everywhere."""

from __future__ import annotations

import base64
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
EXT = ROOT / "extension"
FIX = Path(__file__).resolve().parent / "fixtures" / "extension"

APPLICANT = {"fullName": "Asha Rao", "email": "asha@example.com", "phone": "+91 98765 43210", "city": "Bengaluru",
             "linkedin": "https://www.linkedin.com/in/asha", "portfolio": "https://asha.dev", "noticePeriod": "30 days",
             "expectedCtcLpa": 14, "workAuthIndia": "Yes", "sponsorshipAbroad": "Not applicable, remote only", "gender": "Woman"}
RESUME = {"b64": base64.b64encode(b"%PDF-1.4 test").decode(), "name": "Asha-Rao.pdf", "type": "application/pdf"}


def test_manifest_asks_for_little():
    m = json.loads((EXT / "manifest.json").read_text())
    assert m["manifest_version"] == 3
    assert set(m["permissions"]) == {"activeTab", "scripting", "storage"}  # no tabs, no history, no cookies
    assert "host_permissions" not in m and "content_scripts" not in m  # runs only when you press Fill
    for f in ("popup.html", "popup.js", "fill.js", "icons/icon-128.png"):
        assert (EXT / f).exists(), f


def test_scripts_never_submit():
    for f in ("fill.js", "popup.js"):
        src = (EXT / f).read_text()
        assert ".submit(" not in src and "requestSubmit" not in src
        assert "eval(" not in src and "new Function" not in src


@pytest.fixture(scope="module")
def browser():
    sync = pytest.importorskip("playwright.sync_api")
    try:
        pw = sync.sync_playwright().start()
        b = pw.chromium.launch()
    except Exception as e:  # noqa: BLE001 - no browser on this machine
        pytest.skip(f"Chromium isn't available: {e}")
    yield b
    b.close()
    pw.stop()


def _open(browser, fixture: str, url: str):
    page = browser.new_page()
    html = (FIX / fixture).read_text()
    page.route(url, lambda route: route.fulfill(status=200, content_type="text/html", body=html))
    page.goto(url)
    page.add_script_tag(path=str(EXT / "fill.js"))
    return page


def test_fills_a_greenhouse_form_and_leaves_the_rest_to_you(browser):
    page = _open(browser, "greenhouse.html", "https://job-boards.greenhouse.io/acme/jobs/123")
    r = page.evaluate("d => window.__careerosFill(d)", {"applicant": APPLICANT, "resume": RESUME})
    val = lambda sel: page.eval_on_selector(sel, "e => e.value")  # noqa: E731
    assert val("#first_name") == "Asha" and val("#last_name") == "Rao" and val("#email") == "asha@example.com"
    assert val("#phone") == "+91 90000 00000"  # what was already typed stays
    assert val("#q1") == "https://www.linkedin.com/in/asha" and val("#q2") == "https://asha.dev"
    assert page.eval_on_selector("#q3", "e => e.options[e.selectedIndex].text") == "Yes"
    assert page.eval_on_selector('input[name=q4][value=no]', "e => e.checked")  # "remote only" means no sponsorship needed
    assert page.eval_on_selector("#q5", "e => e.options[e.selectedIndex].text") == "30 days"
    assert val("#q6") == "14"
    assert page.eval_on_selector("#resume", "e => e.files.length && e.files[0].name") == "Asha-Rao.pdf" and r["resume"] == "attached"
    assert page.eval_on_selector("#cover", "e => e.files.length") == 0
    # Never filled: voluntary questions, someone else's details, private numbers, passwords, consent boxes.
    assert page.eval_on_selector("#q8", "e => e.selectedIndex") == 0
    assert val("#q9") == "" and val("#q10") == "" and val("#q11") == "" and val("#pw") == ""
    assert not page.eval_on_selector("#consent", "e => e.checked")
    assert not page.evaluate("window.submitted")
    needs = " | ".join(n["label"] for n in r["needs"])
    assert "Why do you want to work at Acme" in needs and "PAN" in needs and "privacy notice" in needs
    assert r["skippedSensitive"] >= 2
    assert page.eval_on_selector("#first_name", "e => e.dataset.careeros") == "filled"
    assert page.eval_on_selector("#q7", "e => e.dataset.careeros") == "needs"
    info = page.evaluate("window.__careerosRead()")
    assert info["title"] == "AI Engineer" and info["company"] == "Acme"
    page.close()


def test_controlled_inputs_see_the_change(browser):
    page = _open(browser, "react.html", "https://jobs.ashbyhq.com/acme/1/application")
    page.evaluate("d => window.__careerosFill(d)", {"applicant": APPLICANT, "resume": None})
    assert page.evaluate("window.state") == {"fullName": "Asha Rao", "email": "asha@example.com", "city": "Bengaluru"}
    page.close()


@pytest.mark.parametrize("url", ["https://www.linkedin.com/jobs/view/1/apply", "https://www.naukri.com/job-listings-x",
                                 "https://in.indeed.com/viewjob?jk=1", "https://wellfound.com/jobs/1"])
def test_never_runs_on_big_job_boards(browser, url):
    page = _open(browser, "greenhouse.html", url)
    r = page.evaluate("d => window.__careerosFill(d)", {"applicant": APPLICANT, "resume": RESUME})
    assert r["blocked"] and not r["filled"]
    assert page.eval_on_selector("#first_name", "e => e.value") == ""
    page.close()
