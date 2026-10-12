# The apply agent

## When it may submit on its own
All of these must hold:
1. The kill switch is off (`careeros resume`).
2. The role is `ready` with a passing review, or you approved it.
3. Every **required** field resolved to `high` or `medium` confidence (set `allow_inferred_answers = false` in your profile to require `high`).
4. No captcha, login wall or "already applied" notice on the page.
5. The company has no submitted application in the last 180 days.
6. Today's count is under your daily cap.

Otherwise the role stays in your batch with the exact reasons, for example:
`'Why do you want to work at Demo Co?': Required: an essay question nobody has answered yet.`

## How answers are resolved
`careeros/apply/answers.py`, in order:

1. **Never auto-filled**: Aadhaar, PAN, passport, bank details, date of birth, passwords. Always escalated.
2. **Diversity questions**: "Decline to self-identify" (or your profile's answer).
3. **Profile fields**: name, email, phone, links, location, education, CTC, notice, start date, sponsorship, work authorization (country-aware), relocation, languages.
4. **Brain-derived**: "years of experience with X" from the skill graph (`medium`).
5. **Reviewed package answers**: exact question match (`high`), similar wording (`medium`).
6. **Select / radio options**: exact, prefix and contains matches; numeric ranges ("16–30 days", "1–3 years"); yes/no synonyms.
7. Anything else: optional → left blank; required → escalated.

Work-authorization questions are answered from `terms.work_authorization`. If a
question doesn't name a country and the role is abroad, it escalates rather
than guess.

## What happens on submit
1. `begin_submit` writes a `submitting` row keyed by company + canonical URL.
2. The form is filled and screenshotted (`receipts/<time>-<job>/filled.png`).
3. Submit is clicked once.
4. The page is checked for a confirmation ("Thank you for applying", "application received").
5. Confirmed → row becomes `submitted`, job becomes `applied`, `after-submit.png` saved.
6. Not confirmed → the row stays `submitting`. Every later attempt raises `NeedsHumanCheck` until you check the site or your inbox and clear it.

## Hosted auto-apply (Claude desktop app)
With the hosted dashboard, a scheduled task follows [prompts/scheduled-apply.md](../prompts/scheduled-apply.md).
It runs on your computer through the Claude desktop app, in its built-in browser
(or Claude in Chrome), so it uses the sign-ins you made there and never sees a
password.

1. **Check in.** It writes `settings/applyRunner`, which the dashboard shows as "Your computer: linked".
2. **Inputs.** Your saved application details (`profile/applicant`), the resume PDF you uploaded, and the Career Brain once built.
3. **Order.** Roles you queued, then roles you approved, then (with the switch on) roles whose must-haves your evidence covers. Newest and remote-worldwide first; at most one role per company per run; never past the daily cap.
4. **Fit check** for roles it picked itself: each must-have needs evidence in your resume or brain, and the evidence map and gaps are saved to the role.
5. **Fill.** Every field from your details; honest "No" where your evidence doesn't show a skill; short answers with one real proof point; diversity questions declined.
6. **Stop rules.** Sign-in or account pages, captchas, one-time codes, ID numbers, assessments, long essays and any guessed answer stop that role and list it under *Auto-apply needs you* with the reason, the form link, and *Try again* / *I applied* buttons.
7. **Submit once**, confirm from the page or your inbox, and record the confirmation and the resume version that was sent.

## Platform rules
- Company ATS pages (Greenhouse, Lever, Ashby, Workday, career sites) are the intended targets.
- No automation of LinkedIn (including Easy Apply) or Indeed Apply; both prohibit it.
- No account creation, passwords, OTPs or captcha solving.
- Polite pacing: one request per host per second in the scouts; one submission at a time.

## Timing
Submissions are most effective early in the employer's working day and soon
after posting. With a schedule, run the apply step in the morning of the
employer's time zone, and immediately for roles under 6 hours old.
