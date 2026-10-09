"""Fill an application form in a real browser, and submit only when it's safe.

Flow
  1. Open the posting's apply page (the company's own ATS page, never an aggregator copy).
  2. Stop if there's a captcha, a login wall or an "already applied" notice.
  3. Read every field: label, type, required, options.
  4. Resolve each field with `answers.resolve` (profile, brain, approved package).
  5. Fill everything that resolved; screenshot the filled form.
  6. Submit only if: `submit=True`, every required field resolved, the kill
     switch is off, and the state machine says this role was never submitted.
  7. Confirm success from the page, screenshot it, and store a receipt.

CareerOS never solves captchas, never creates accounts and never enters
passwords. Those cases go to you.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from ..store import AlreadySubmitted, NeedsHumanCheck, Paused, Store
from .answers import ESCALATE, SKIP, Context, Field, Resolution, ready_to_submit, resolve

EXTRACT_JS = r"""
() => {
  const out = []; const seenRadio = new Set(); let n = 0;
  const T = el => (el ? (el.innerText || el.textContent || '') : '').replace(/\s+/g, ' ').trim();
  const visible = el => { const r = el.getBoundingClientRect(); const s = getComputedStyle(el); return r.width > 0 && r.height > 0 && s.visibility !== 'hidden' && s.display !== 'none'; };
  const labelFor = el => {
    if (el.id) { const l = document.querySelector('label[for="' + CSS.escape(el.id) + '"]'); if (l && T(l)) return T(l); }
    const wrap = el.closest('label'); if (wrap && T(wrap)) return T(wrap);
    if (el.getAttribute('aria-label')) return el.getAttribute('aria-label');
    const lb = el.getAttribute('aria-labelledby'); if (lb) return lb.split(/\s+/).map(id => T(document.getElementById(id))).join(' ');
    const box = el.closest('.field, .application-question, .form-group, [class*="field"], [class*="question"]');
    if (box) { const l = box.querySelector('label, legend, .label, .application-label'); if (l && T(l)) return T(l); }
    return el.getAttribute('placeholder') || el.name || '';
  };
  const req = (el, label) => el.required || el.getAttribute('aria-required') === 'true' || /\*\s*$/.test(label);
  for (const el of document.querySelectorAll('input, select, textarea')) {
    let type = el.tagName === 'SELECT' ? 'select' : el.tagName === 'TEXTAREA' ? 'textarea' : (el.type || 'text').toLowerCase();
    if (['hidden', 'submit', 'button', 'image', 'reset', 'password', 'search'].includes(type) || el.disabled) continue;
    if (el.getAttribute('role') === 'combobox') type = 'combobox';
    if (!['file', 'radio', 'checkbox'].includes(type) && !visible(el)) continue;
    if (type === 'radio') {
      if (seenRadio.has(el.name)) continue; seenRadio.add(el.name);
      const group = [...document.querySelectorAll('input[type=radio][name="' + CSS.escape(el.name) + '"]')];
      const id = 'cos-' + (n++);
      group.forEach((g, i) => g.setAttribute('data-careeros-id', id + '-' + i));
      const opts = group.map(g => labelFor(g));
      const fs = el.closest('fieldset');
      let label = fs && fs.querySelector('legend') ? T(fs.querySelector('legend')) : '';
      if (!label) {
        let box = el.parentElement;
        while (box && !group.every(g => box.contains(g))) box = box.parentElement;
        if (box) { label = T(box); for (const o of opts) label = label.replace(o, ''); label = label.trim(); }
      }
      out.push({key: id, label, type: 'radio', required: group.some(g => g.required) || /\*/.test(label), options: opts, name: el.name});
      continue;
    }
    const id = 'cos-' + (n++);
    el.setAttribute('data-careeros-id', id);
    const label = labelFor(el);
    const options = type === 'select' ? [...el.options].map(o => o.text.trim()) : [];
    out.push({key: id, label, type, required: req(el, label), options, name: el.name || ''});
  }
  return out;
}
"""

BLOCKERS_JS = r"""
() => {
  const vis = el => { const r = el.getBoundingClientRect(); return r.width > 0 && r.height > 0; };
  const found = [];
  for (const sel of ['.g-recaptcha:not([data-size="invisible"])', '.h-captcha', 'iframe[src*="hcaptcha"]', 'iframe[src*="challenges.cloudflare"]', 'iframe[title*="challenge" i]', '#cf-challenge-running'])
    for (const el of document.querySelectorAll(sel)) if (vis(el)) found.push('captcha');
  if (document.querySelector('input[type=password]')) found.push('login');
  if (/you('ve| have) already applied|already submitted an application/i.test(document.body.innerText)) found.push('already-applied');
  return [...new Set(found)];
}
"""

CONFIRM = re.compile(
    r"thank you for (applying|your application|your interest)|thanks for applying|application (has been |was )?(received|submitted)|"
    r"we('ve| have) received your application|successfully (submitted|applied)",
    re.I,
)


@dataclass
class RunResult:
    url: str
    fields: list[dict] = field(default_factory=list)
    resolutions: list[dict] = field(default_factory=list)
    blockers: list[str] = field(default_factory=list)
    needs_you: list[str] = field(default_factory=list)
    submitted: bool = False
    confirmed: bool = False
    receipt_dir: str = ""
    errors: list[str] = field(default_factory=list)

    @property
    def status(self) -> str:
        if self.submitted and self.confirmed:
            return "applied"
        if self.submitted:
            return "submitted-unconfirmed"
        if self.blockers or self.needs_you or self.errors:
            return "needs-you"
        return "ready"


def _fill(page, res: Resolution) -> None:
    f, v = res.field, res.value
    if v is None or res.confidence in (ESCALATE, SKIP):
        return
    if f.type == "radio":
        idx = next((i for i, o in enumerate(f.options) if o == v), None)
        if idx is not None:
            page.locator(f'[data-careeros-id="{f.key}-{idx}"]').check(force=True)
        return
    loc = page.locator(f'[data-careeros-id="{f.key}"]')
    if f.type == "select":
        loc.select_option(label=str(v))
    elif f.type == "checkbox":
        loc.check(force=True) if v else loc.uncheck(force=True)
    elif f.type == "file":
        loc.set_input_files(str(v))
    elif f.type == "combobox":
        loc.fill(str(v))
        loc.press("Enter")
    else:
        loc.fill(str(v))


def run(
    url: str,
    ctx: Context,
    *,
    submit: bool = False,
    store: Store | None = None,
    job_id: str = "",
    receipts_dir: str | Path = "receipts",
    headed: bool = False,
    allow_medium: bool = True,
    timeout_ms: int = 30000,
) -> RunResult:
    from playwright.sync_api import sync_playwright  # optional dependency

    result = RunResult(url=url)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    rdir = Path(receipts_dir) / f"{stamp}-{job_id or hashlib.sha1(url.encode()).hexdigest()[:8]}"
    rdir.mkdir(parents=True, exist_ok=True)
    result.receipt_dir = str(rdir)

    launch = {"headless": not headed}
    if os.environ.get("CAREEROS_CHROMIUM"):
        launch["executable_path"] = os.environ["CAREEROS_CHROMIUM"]
    with sync_playwright() as p:
        browser = p.chromium.launch(**launch)
        page = browser.new_page()
        page.set_default_timeout(timeout_ms)
        try:
            page.goto(url, wait_until="domcontentloaded")
            page.wait_for_timeout(800)
            result.blockers = page.evaluate(BLOCKERS_JS)
            raw = page.evaluate(EXTRACT_JS)
            fields = [Field(r["key"], r["label"], r["type"], bool(r["required"]), r.get("options", []), r.get("name", "")) for r in raw]
            result.fields = raw
            resolutions = [resolve(f, ctx) for f in fields]
            result.resolutions = [r.to_dict() for r in resolutions]
            ok, reasons = ready_to_submit(resolutions, allow_medium=allow_medium)
            result.needs_you = reasons
            for r in resolutions:
                try:
                    _fill(page, r)
                except Exception as e:  # a field we couldn't fill is a reason to stop, not to guess
                    result.errors.append(f"Couldn't fill '{r.field.label}': {e.__class__.__name__}")
            page.screenshot(path=str(rdir / "filled.png"), full_page=True)

            can_submit = submit and ok and not result.blockers and not result.errors
            key = None
            if can_submit and store is not None:
                try:
                    key = store.begin_submit(job_id or url, ctx.job | {"url": ctx.job.get("url", url)})
                except (AlreadySubmitted, NeedsHumanCheck, Paused) as e:
                    result.blockers.append(str(e))
                    can_submit = False
            if can_submit:
                btn = page.locator('button[type=submit], input[type=submit]').filter(visible=True)
                if btn.count() == 0:
                    btn = page.get_by_role("button", name=re.compile(r"submit|apply", re.I))
                btn.first.click()
                result.submitted = True
                try:
                    page.wait_for_load_state("networkidle", timeout=15000)
                except Exception:
                    pass
                page.wait_for_timeout(1000)
                body = page.inner_text("body")
                result.confirmed = bool(CONFIRM.search(body))
                invalid = page.locator('[aria-invalid="true"]').count()
                if not result.confirmed and invalid:
                    result.errors.append(f"The form reported {invalid} invalid field(s) after submit.")
                page.screenshot(path=str(rdir / "after-submit.png"), full_page=True)
                if store is not None and key:
                    receipt = {"job_id": job_id, "url": url, "at": stamp, "confirmed": result.confirmed, "dir": str(rdir)}
                    # Unconfirmed submits stay "submitting" so nothing retries blindly.
                    if result.confirmed:
                        store.finish_submit(key, True, receipt)
        finally:
            (rdir / "result.json").write_text(json.dumps(result.__dict__ | {"status": result.status}, indent=2, default=str), encoding="utf-8")
            browser.close()
    return result
