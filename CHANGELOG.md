# Changelog

All notable changes to CareerOS. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses [semantic versioning](https://semver.org/).

## [1.0.0] - 2026-11-04

### Added
- **Bring your own model.** `careeros/llm.py` calls Anthropic, OpenAI (and any OpenAI-compatible API through `OPENAI_BASE_URL`), Google Gemini or a local Ollama model with your own key, using only the standard library. Configure it in `.env`; `careeros llm` shows the provider and model (never the key) and `careeros llm test` checks it.
- **AI commands with code checks.** `careeros ai profile`, `careeros ai posting` and `careeros ai evaluate`. Values the resume doesn't contain are dropped and listed; requirements are kept only with a verbatim quote; evaluations must pass the same validator as `careeros eval-check`, with one retry.
- **Dashboard on your model.** When a key is configured, the local dashboard's AI actions run through `/api/ai`, which accepts only same-origin JSON requests.
- **Project website and docs** in `website/`, deployed to GitHub Pages with the job board at `jobs.html` and the dashboard demo at `demo/`.
- `pages.yml` workflow to publish the site on every change; security policy, code of conduct, issue and pull request templates.

## Before 1.0

### 2026-10-29

- Referral finder after each application, junior engineers first, with a drafted note per person.
- "Apply yourself" rows for roles listed only on LinkedIn, Naukri or Wellfound, with answers prepared.
- One record per role across reposts, legal-name variants and location suffixes.
- Dashboard: Auto-apply page, Inbox from Gmail, 12 resume themes and a theme builder, applications board, application pages with AI tailoring, calendar and export.

### 2026-10-23

- Scoring, posting checks, documents, tracking and interview tools (ideas adapted from career-ops, MIT).
- Hiring radar, funding radar, a deep sweep of about 20,000 ATS boards, published pay ranges and a 20 LPA+ pay tier.
- YC companies as a scanned source.

### 2026-10-13

- CareerOS Cloud: a multi-user service with accounts, per-user pipelines, a worker with a durable task queue, an agent API and Docker Compose and Render deploy files.

### 2026-10-12

- Public job board on GitHub Pages with a JSON API and RSS, rebuilt by the hourly scan.
- Auto-apply switch, application details and resume upload on the dashboard, and the scheduled apply prompt.

### 2026-10-09 (first release)

- First release: gates with quotes, the India feed (1,396 companies across 8 hiring systems and 9 remote boards), the 96-platform registry, the claims checker, the apply agent with a one-submit state machine, agent skills and the local dashboard.
