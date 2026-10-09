"""Browser tests against a local Greenhouse-style form. Skipped if Playwright/Chromium isn't installed."""

import json
import tomllib
from pathlib import Path

import pytest

pytest.importorskip("playwright.sync_api")

from careeros.apply import runner  # noqa: E402
from careeros.apply.answers import Context  # noqa: E402
from careeros.store import Store  # noqa: E402

ROOT = Path(__file__).parents[1]
FORM = (ROOT / "tests" / "fixtures" / "form.html").resolve().as_uri()
PROFILE = tomllib.loads((ROOT / "config" / "profile.example.toml").read_text())
BRAIN = json.loads((ROOT / "brain" / "brain.example.json").read_text())
JOB = {"company": "Demo Co", "title": "Applied AI Engineer", "url": FORM, "location": "Bengaluru", "region": "south-india"}


def _browser_ok():
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            p.chromium.launch().close()
        return True
    except Exception:
        return False


pytestmark = pytest.mark.skipif(not _browser_ok(), reason="Chromium for Playwright isn't installed")


@pytest.fixture
def resume(tmp_path):
    f = tmp_path / "resume.pdf"
    f.write_bytes(b"%PDF-1.4\n% test resume\n")
    return f


def test_dry_run_escalates_essay(tmp_path, resume):
    ctx = Context(PROFILE, BRAIN, {"resume": str(resume)}, JOB)
    res = runner.run(FORM, ctx, submit=True, receipts_dir=tmp_path)
    labels = {f["label"] for f in res.fields}
    assert {"First Name *", "Email *", "Notice period *"} <= labels
    assert not res.submitted
    assert any("Why do you want to work at Demo Co?" in r for r in res.needs_you)
    assert (Path(res.receipt_dir) / "filled.png").exists()
    by_label = {r["label"]: r for r in res.resolutions}
    assert by_label["Notice period *"]["value"] == "Up to 30 days"
    assert by_label["Gender"]["value"] == "Decline to self-identify"
    assert by_label["Favourite programming meme"]["confidence"] == "skip"


def test_full_submit_then_idempotent(tmp_path, resume):
    store = Store(tmp_path / "t.db")
    pkg = {"resume": str(resume), "answers": {"Why do you want to work at Demo Co?": "Your eval tooling is the problem I've been solving in TicketRouter."}}
    ctx = Context(PROFILE, BRAIN, pkg, JOB)
    res = runner.run(FORM, ctx, submit=True, store=store, job_id="demo-co-applied-ai", receipts_dir=tmp_path)
    assert res.submitted and res.confirmed and res.status == "applied", (res.needs_you, res.errors, res.blockers)
    again = runner.run(FORM, ctx, submit=True, store=store, job_id="demo-co-applied-ai", receipts_dir=tmp_path)
    assert not again.submitted and any("already submitted" in b for b in again.blockers)


def test_captcha_blocks(tmp_path, resume):
    html = (ROOT / "tests" / "fixtures" / "form.html").read_text().replace(
        '<button type="submit">', '<div class="g-recaptcha" style="width:300px;height:80px"></div><button type="submit">')
    page = tmp_path / "captcha.html"
    page.write_text(html)
    pkg = {"resume": str(resume), "answers": {"Why do you want to work at Demo Co?": "x"}}
    res = runner.run(page.as_uri(), Context(PROFILE, BRAIN, pkg, JOB), submit=True, receipts_dir=tmp_path)
    assert "captcha" in res.blockers and not res.submitted
