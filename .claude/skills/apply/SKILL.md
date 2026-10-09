---
name: apply
description: Submit approved or auto-eligible applications on the company's own application page, filling every field from the profile, brain and reviewed package, stopping for anything that needs the user. Use for "apply to X" and for scheduled apply runs.
---

# Apply

An application can't be taken back. This skill submits only when every rule
below holds, and otherwise leaves the job in the batch with the exact reason.

## Before opening any page
- `careeros` is not paused (`careeros resume` was the last kill-switch command).
- The job is at stage `ready` with `review.json` verdict `pass` (or `approved` by the user).
- Today's submissions are under the daily cap in `config/settings.toml`.
- The company has no application in the last 180 days (the store enforces this).

## Greenhouse, Lever, Ashby (and simple forms)
Dry run first, then submit if it comes back clean:
```bash
careeros apply "<apply url>" --job-id <id> --package packages/<id>/package.json
careeros apply "<apply url>" --job-id <id> --package packages/<id>/package.json --submit
```
The runner reads every field, resolves answers with a confidence, fills,
screenshots, and submits only if every required field resolved. It stops on
captchas, login walls and "already applied" notices, and its state machine
makes a second submit impossible.

## Other forms (Workday, custom sites) in a browser
Use the browser the user prefers (Claude in Chrome, Claude's built-in browser,
or Antigravity's browser agent) and follow the same rules by hand:
1. Open the company's own apply page.
2. Answer each field with the rules in `careeros/apply/answers.py`: profile first, brain second, reviewed package answers third. Decline diversity questions unless the profile says otherwise.
3. Stop and hand to the user for: captcha, account creation, passwords, OTPs, Aadhaar/PAN/passport/bank/date of birth, legal attestations, assessments, an essay with no reviewed answer, or any answer you'd have to guess.
4. Before submit, check: right resume version uploaded, email and phone match the profile, no placeholder text, every required field filled. Screenshot it.
5. Submit once. Wait for the confirmation page or email. Screenshot it.

## After
- Confirmed → stage `applied`, `appliedAt`, receipt path, timeline event.
- Not confirmed → leave it marked as submitting, tell the user, and don't retry until they've checked the site or their email.
- Then hand off to `outreach` for the hiring-manager note and to `tracker`.

## Never
- Apply through LinkedIn Easy Apply, Indeed Apply or any platform whose terms forbid automation.
- Create accounts or enter passwords on the user's behalf.
- Solve or bypass a captcha.
