---
name: tailor
description: Produce a truthful, role-specific application package (resume JSON and PDF, cover note, screening answers) from the Career Brain for one job, and pass it through the claims checker.
---

# Tailor

Output goes to `packages/<job-id>/`:
- `resume.json`: `{summary, skills[], bullets[{text, refs[]}]}`; every bullet names the brain claims it is built from.
- `resume.pdf`: single column, standard headings, reverse chronological, no tables or graphics. CGPA/percentage for every qualification (Indian convention).
- `package.json`: `{resume: "packages/<id>/resume.pdf", cover_note, answers: {question: answer}}` (read by `careeros apply`).

## Steps
1. Read the job's brief, evidence map and gaps.
2. Pick the positioning variant the evidence supports (AI Engineer, AI Automation Engineer, ...). Never one it doesn't.
3. Select and order claims by relevance to the brief's three problems. Drop the rest.
4. Write bullets: specific verb, what you built, the number, the tool. 60%+ of bullets carry a number. Mirror the posting's exact tool names only where the claim uses that tool.
5. Title alignment: use the posted title in the headline only if it's honest.
6. Cover note (120–180 words): the company's problem from the brief, one proof point, one ask. Skip it if the form doesn't want one.
7. Screening answers: answer from the brain and profile. Questions you can't answer truthfully go to the user.
8. Run the gate. Fix every BLOCK line; never "fix" by deleting the ref.
   ```bash
   careeros claims-check packages/<id>/resume.json --brain brain/brain.json
   ```
9. Hand off to the `reviewer` skill. Don't mark the job ready yourself.

## Voice
Use the brain's voice profile. Banned by default: leverage, spearhead, synergy,
results-driven, passionate, cutting-edge, "responsible for". Vary sentence
length. A bullet that could belong to any candidate gets rewritten.
