# Contributing

Thanks for helping. A few rules keep CareerOS accurate and safe.

1. **Tests first.** Every change to extraction, gates, dedupe, claims or answers comes with a test. If a real posting fooled a gate, add its text (trimmed, with company names replaced) as a test case.
2. **No fabrication paths.** Don't add anything that writes a claim, number or answer the brain or profile can't back up. When unsure, escalate to the user.
3. **No prohibited automation.** No LinkedIn or Indeed automation, captcha solving, account creation or credential handling.
4. **Standard library in the core.** New runtime dependencies need a strong reason.
5. **Dashboard edits** go in `dashboard/app.html`; run `python scripts/build_dashboard.py` afterwards.
6. **No personal data** in issues, fixtures or screenshots.

Run `python -m pytest -q` before opening a pull request.
