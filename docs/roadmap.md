# Roadmap

Status of the build order from the CareerOS blueprint.

| Phase | Scope | Status |
|---|---|---|
| 0. Truth layer | Brain schema, evidence vault, temporal status, `brain-check`, claims gate | **Done** |
| 1. Discovery and gating | Greenhouse/Lever/Ashby scouts, agent scout for other boards, 9 gates with quotes, dedupe, skip log | **Done** |
| 2. Generation | Research brief, decision A–F, tailoring skill, cover notes, screening answers | **Done** as skills; PDF rendering template planned |
| 3. Control plane | Dashboard, approvals, skip-log overrides, audit log, kill switch | **Done** |
| 4. Browser execution | Answer resolver, Playwright filler with dry run, idempotent submit, receipts, stop rules | **Done** for standard forms; Workday via the browser agent |
| 5. Learning | Funnel, skip mining, gap map, weekly experiment | **Skill** done; automatic score calibration planned |
| 6. Interview | Interview pack, mock interviews, negotiation brief | **Skill** done |
| 7. Autonomous operations | Scheduled search and apply prompts, caps, timing | **Done** (hosted and cron) |

## Next
- Resume PDF renderer from `resume.json` with a multi-parser round-trip test.
- Workday and SmartRecruiters scouts.
- Score calibration from your own outcomes once there are enough of them.
- Proof-of-work builder: a small, real artifact per Reach-tier company.
- Evaluation harness: golden postings with known-correct gate results, run in CI.

Contributions welcome; see `CONTRIBUTING.md`.
