---
name: career-brain
description: Build or update the Career Brain (brain/brain.json) by interviewing the user and reading their resume, LinkedIn export, GitHub and portfolio. Use before any tailoring, and whenever the user ships something new.
---

# Career Brain

The brain is the only source the rest of the system may draw on. Tailoring
quality is capped by how rich and honest this file is, so take your time.

## Inputs
- Resume (PDF/DOCX), LinkedIn PDF export, GitHub profile, portfolio links.
- The user's answers. Interview them; don't infer.

## Steps
1. Copy `brain/brain.example.json` to `brain/brain.json` if it doesn't exist. Read the example to learn the schema.
2. Extract every role, internship, freelance client, project and course from the documents.
3. For each one, interview the user until you have **problem → action → tools → outcome → proof**:
   - What was broken or slow before? Who cared?
   - What did *you* do (not the team)?
   - Which tools, exactly?
   - What changed, with a number if one exists (time, money, users, accuracy, volume)?
   - Where's the proof (repo, demo, screenshot, doc, testimonial, invoice, certificate)?
4. Mark each item's status: `past`, `current`, `in_progress`, `planned` or `retired`. Planned work is never written up as done.
5. Add every proof to `evidence[]` with an id, and link it from the claim.
6. Build the skill graph: proficiency 1–5, years, last used, linked evidence. Years must add up against the roles.
7. Collect 6–12 STAR stories (ownership, ambiguity, conflict, failure, speed, impact), each linked to claims.
8. Capture the voice profile: 3 writing samples from the user, preferred verbs, banned words.
9. Run `careeros brain-check brain/brain.json`. Fix every problem it lists, or mark the claim `retired` if there's no proof.
10. Show the user a one-page summary and have them confirm each claim line by line.

## Rules
- Never round numbers up. "About 30%" stays "about 30%".
- If the user can't name proof, the claim stays in the brain with no evidence, and `brain-check` keeps it off resumes.
- Don't store passwords, Aadhaar, PAN, bank or passport numbers here.
- When the hosted dashboard is in use, set `brain/status` to `{state: "ready", summary, counts}` once the user has confirmed.
