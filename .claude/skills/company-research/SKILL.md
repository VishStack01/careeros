---
name: company-research
description: Build a company and role brief for a kept job - what the company does, why it's hiring now, the three problems the team needs solved, stack, pay band, interview process - plus a fit score by dimension and an A-F decision.
---

# Company research and decision

## Brief (write into the job's `brief`)
- **about**: one sentence on the product and who pays for it.
- **team / whyNow**: what this team owns and why the role exists now (launch, scale, backfill). Cite sources.
- **problems**: the three problems the hiring manager is trying to solve, in their words where possible. This is the "role decoder".
- **stack**: exact tool names from the posting, engineering blog and public repos.
- **salaryBand**: the posting's range, then public sources (Levels.fyi, Glassdoor, AmbitionBox) labelled as such.
- **interviewIntel**: rounds, take-homes, timelines from public interview reports.
- **sources**: every URL you used.

## Fit by dimension (write `dimensions`, `evidence`, `gaps`)
Rate 0–3 with a one-line reason that cites the brain: skill evidence,
experience, project relevance, impact proof, company fit, location,
authorization, compensation, strategic value.

Build the **evidence map**: each must-have requirement → the brain claim that
proves it (with its id). Requirements with no claim go into `gaps`. Never fill
a gap with a guess.

Never output an ATS percentage or "shortlist probability". Nobody outside the
company can measure it.

## Decision (write `decision`, `decisionReason`, `fitBand`)
- **A** Apply now: strong evidence for every must-have, good ROI.
- **B** Tailor further: promising, but the proof needs strengthening first.
- **C** Network first: high value and a warm path exists.
- **D** Build proof first: a strategic gap worth closing before applying.
- **E** Your call: ambiguous or consequential.
- **F** Skip: low fit or poor return.
