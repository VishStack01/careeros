# How it works, step by step

Follow one role from posting to interview.

## 1. You build the brain once
The `career-brain` skill interviews you and reads your resume, LinkedIn export,
GitHub and portfolio. Every role, internship, client and project becomes a
claim: **problem → action → tools → outcome → proof**, with a status (past,
current, in progress, planned, retired). `careeros brain-check` refuses claims
without evidence. This file is the ceiling on everything that follows.

## 2. The scout finds the role
Every few hours `careeros scout` pulls the public job feeds of the companies on
your watchlist, and the `job-scout` skill searches boards without APIs. A role
posted 9 hours ago on a company's Ashby board arrives with its real posting
date, location fields and full description.

## 3. The gatekeeper decides, and shows its working
`careeros/gates.py` runs nine gates. Each one records the sentence it relied on:

| Gate | Example verdict | Quote stored |
|---|---|---|
| Role | Target role | "Applied AI Engineer" |
| Seniority | Not stated in title | |
| Experience | Fresher (0 years) | "0–1 years of experience shipping production code; new grads welcome." |
| Posted | Posted 9h ago (priority) | |
| Open | Open | |
| Location | Remote worldwide | "We are remote-first and hire anywhere in the world." |
| Pay | 26–35 LPA | "$30K – $40K" |
| Dealbreaker | None found | |
| Company | Not blocked | |

Fail any gate and the role goes to the skip log with the reason and what would
change it. You can overrule from the dashboard.

## 4. Research and decision
The `company-research` skill writes a brief: what the company does, why it's
hiring now, the three problems the team needs solved, stack, pay band and
interview process, with sources. It rates fit by dimension (each citing a brain
claim), maps each requirement to evidence, lists gaps honestly, and decides:

**A** apply now · **B** tailor further · **C** network first · **D** build proof first · **E** your call · **F** skip.

## 5. Tailoring and the truth gate
The `tailor` skill writes `resume.json` where every bullet names the claims it
comes from, then a PDF, a cover note and screening answers. `careeros
claims-check` blocks any bullet that has no source, uses a number the brain
doesn't contain, names a tool the claim didn't use, or writes up planned work
as done. Then the `reviewer` skill, on a different model, checks
interview-defensibility, does a 6-second recruiter scan and lists the hiring
manager's objections. Only a pass moves the role to **ready**.

## 6. Applying
`careeros apply` opens the company's own form, reads every field and resolves
each answer with a confidence:

- **high**: copied from your profile or the reviewed package
- **medium**: derived, such as years of Python from the brain, or a fuzzy option match
- **escalate**: sensitive fields, essays nobody wrote, legal questions without a clear answer

If every required field is high or medium, it fills, screenshots, submits once,
waits for the confirmation, screenshots again and stores a receipt. If not, the
role waits in your batch with the exact questions it needs you for. Captchas,
logins and passwords always go to you.

## 7. Outreach, tracking, learning
The `outreach` skill drafts the hiring-manager note, the recruiter note, a
LinkedIn note and day 3/7/14 follow-ups; you send them. The `tracker` reads
your inbox and moves roles to screen, interview or rejected. The
`weekly-review` skill reports the funnel, mines skip reasons, builds the gap map
and runs one experiment a week.
