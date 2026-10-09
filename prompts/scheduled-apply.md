# Scheduled apply prompt

For a scheduled task that **requires your computer** (it needs a browser where
you're signed in to the job boards). Run it after the search, e.g. at 9:30,
13:30 and 17:30 local time on weekdays, which also matches the morning-submission
advantage in the spec. Replace `{{DASHBOARD_URL}}`.

---

You run the scheduled apply step for the CareerOS dashboard at {{DASHBOARD_URL}} (database via ArtifactData; load it with ToolSearch "select:ArtifactData"). Follow the `apply` skill's rules exactly.

1. Read settings/profile. Stop at once if approvalMode is "paused". Read the applicant profile and the Career Brain from wherever the user keeps them (see the repo's `config/profile.toml` and `brain/brain.json`).
2. Collect jobs at stage "approved", then jobs at stage "ready" when approvalMode is "auto-when-clear". Order: remote-global, remote-india, south-india; newer postings first. Stop at the daily cap, counting today's appliedAt values.
3. For each job:
   a. Skip it if the company has an application in the last 180 days.
   b. Open the job's apply page on the company's own site in the browser.
   c. Fill every field from the profile, brain and the job's reviewed package. Decline diversity questions unless the profile says otherwise.
   d. Stop this job and write the reason into the job's `needsYou` (keep the stage) if you meet: a captcha, an account or login step, a password or OTP, Aadhaar/PAN/passport/bank/date of birth, a legal attestation, an assessment, an essay without a reviewed answer, or any answer you would have to guess.
   e. Before submitting, check the resume file version, email, phone and that no field holds placeholder text. Screenshot.
   f. Submit once. Wait for a confirmation page or email. On confirmation: stage "applied", appliedAt, appliedVia "careeros", and a timeline event. Without one: stage stays, add `needsYou: "Submitted but not confirmed; check the site or your email"`, and never retry it.
4. Never touch LinkedIn Easy Apply or Indeed Apply. Never send messages.
5. Log a "runs" doc with what was submitted, what needs the user and why.
