---
name: reviewer
description: Independent review of an application package before it can be sent - hallucination gate, interview-defensibility, 6-second recruiter scan and hiring-manager objections. Run it with a different model from the one that wrote the package (e.g. Codex reviewing Claude's work).
---

# Reviewer

The drafter must not grade its own work. Run this skill in a separate session,
ideally on a different model, with only: the job brief, the brain, and the package.

## Checks (any FAIL blocks the package)
1. **Claims gate**: `careeros claims-check` passes with no BLOCK lines.
2. **Hallucination read**: for each bullet, open the referenced claim and confirm the bullet says nothing the claim doesn't (scope, title, team size, client names, dates).
3. **Interview-defensibility**: could the candidate talk about this bullet for three minutes? Flag thin ones.
4. **6-second scan**: read only title, companies, dates, education, skills. Does this person plausibly fit? Say yes or no and why.
5. **Hiring-manager objections**: list the three strongest objections and where the package answers each. An unanswered objection is a FAIL unless the decision is B, C or D.
6. **Consistency**: titles, dates and numbers match the brain and the user's LinkedIn as recorded in the brain.
7. **Readability**: typos, date formats, PDF metadata (author is the user; no tool names).

## Output
Write `packages/<id>/review.json`: `{verdict: "pass"|"fail", blocks[], warnings[], objections[]}`.
Only on `pass` may the job move to stage `ready`.
