<p align="center">
  <a href="https://vishstack01.github.io/careeros/"><img src="website/assets/og.png" alt="CareerOS: an open-source AI agent for the job search" width="820"></a>
</p>

<h1 align="center">CareerOS</h1>

<p align="center">
  <b>An open-source AI agent for the job search.</b><br>
  It finds fresh roles, checks each one against your rules with quotes from the posting,<br>
  and writes applications from your real experience only. Bring your own model and key.
</p>

<p align="center">
  <a href="https://github.com/VishStack01/careeros/actions/workflows/tests.yml"><img alt="tests" src="https://github.com/VishStack01/careeros/actions/workflows/tests.yml/badge.svg"></a>
  <a href="LICENSE"><img alt="MIT license" src="https://img.shields.io/badge/license-MIT-9AAB63"></a>
  <img alt="Python 3.11 to 3.13" src="https://img.shields.io/badge/python-3.11%20%7C%203.12%20%7C%203.13-B6CAEB">
  <img alt="Bring your own key" src="https://img.shields.io/badge/LLM-Anthropic%20%7C%20OpenAI%20%7C%20Gemini%20%7C%20Ollama-F5B8DB">
  <img alt="No runtime dependencies" src="https://img.shields.io/badge/core-standard%20library%20only-F5D867">
</p>

<p align="center">
  <a href="https://vishstack01.github.io/careeros/"><b>Website</b></a> ·
  <a href="https://vishstack01.github.io/careeros/docs.html"><b>Docs</b></a> ·
  <a href="https://vishstack01.github.io/careeros/jobs.html"><b>Live job board</b></a> ·
  <a href="https://vishstack01.github.io/careeros/demo/"><b>Dashboard demo</b></a>
</p>

---

![CareerOS dashboard: fresh roles, stage cards and today's batch](docs/assets/dashboard-today.png)

## Quick start

```bash
git clone https://github.com/VishStack01/careeros.git && cd careeros
pip install -e .

cp .env.example .env            # pick a provider and paste your key
careeros llm test               # one tiny request; never prints the key

careeros init                   # creates your private, git-ignored config
careeros discover && careeros scan   # map company job boards, build the feed
careeros serve                  # dashboard at http://127.0.0.1:8765
```

No key? Scanning, filtering, tracking and the dashboard all work without a model. A key, or a local Ollama model, adds the AI steps.

## Bring your own model

CareerOS calls the provider you choose with your key, using only Python's standard library (no SDKs).

| Provider | `.env` | Notes |
|---|---|---|
| Anthropic | `CAREEROS_LLM=anthropic`, `ANTHROPIC_API_KEY` | Claude models |
| OpenAI | `CAREEROS_LLM=openai`, `OPENAI_API_KEY` | Set `OPENAI_BASE_URL` for any OpenAI-compatible API (OpenRouter, Groq, Together, vLLM) |
| Google Gemini | `CAREEROS_LLM=gemini`, `GEMINI_API_KEY` | Gemini models |
| Ollama | `CAREEROS_LLM=ollama`, `OLLAMA_HOST` (optional) | Free and fully local |

Pin models with `CAREEROS_MODEL` and `CAREEROS_MODEL_QUICK`. Your key is read at call time, sent only to your provider, and never printed, logged or stored. The local dashboard accepts AI requests only from its own page, so another website can't spend your key.

```bash
careeros ai profile resume.pdf -o profile.json        # resume to profile; unsupported values removed
careeros ai posting posting.txt                       # requirements kept only with a verbatim quote
careeros ai evaluate --jd posting.txt --resume resume.pdf -o eval.json   # 1 to 5 fit, code-checked
```

Every AI output passes a code check before you see it: quotes must appear in the posting, scores must stay inside their dimension ranges, and anything your resume doesn't contain is dropped and listed. A draft that fails gets the errors back once; if it fails again, nothing is written.

## Why it's different

Most job bots optimise the weakest variable: volume. They read job cards instead of postings, invent resume lines, guess form answers and sometimes submit twice. CareerOS is built the other way round.

- **Interviews, not application count.** A daily cap, freshness priority, referral-first decisions and honest skips.
- **Evidence, not keywords.** Every resume line cites a claim in your Career Brain. A code gate blocks numbers, tools or projects the brain can't back up.
- **It shows its work.** Every keep or skip records the exact sentence from the posting that decided it.
- **It scores before it applies.** Each role gets a 1–5 score against your Career Brain, requirement by requirement, with the gaps and how to handle them. Under 4.0, auto-apply waits for you.
- **It applies only when it can answer everything.** Each form answer has a confidence. Sensitive fields, essays nobody wrote, captchas and logins go to you.
- **One submit per role, ever.** An idempotent state machine, receipts with screenshots, and a kill switch.
- **Platform-safe.** No LinkedIn, Naukri, Indeed or Wellfound automation, no account creation, no captcha solving. Outreach is drafted; you send it.
- **Where the openings are first.** About 1,400 product companies' career pages, read straight from their hiring systems every hour, before roles reach the big boards.

## Coverage

| Source | How many | How |
|---|---|---|
| Company career pages | 1,396 product companies: Indian product companies, India engineering centres, the [moreThanFAANGM](https://github.com/Kaustubh-Natuskar/moreThanFAANGM) list, and YC companies in India or hiring remotely | Public feeds of 8 hiring systems (Greenhouse, Lever, Ashby, Workable, SmartRecruiters, Recruitee, Breezy, Personio), scanned every hour on GitHub Actions. [docs/feed.md](docs/feed.md) |
| Remote job boards with feeds | 9 | Remote OK, Remotive, Himalayas, Jobicy, Working Nomads, We Work Remotely, HN jobs, HN "Who is hiring?", Arbeitnow |
| Other platforms | 96 in the registry, 50 low-competition | 26 VC portfolio boards, Indian startup and fresher boards, 11 x-ray searches that find career pages on Keka, Zoho Recruit, Darwinbox and others. [docs/platforms.md](docs/platforms.md) |
| Big boards | LinkedIn, Naukri, Indeed, Wellfound, foundit, Glassdoor, Shine | Their own email alerts only; never automated |

## The job board

The hourly scan also publishes a public job board on GitHub Pages ([jobs.html](https://vishstack01.github.io/careeros/jobs.html)), in the spirit of Arbeitnow: search, filters with counts (where you can work from, experience, posted date, contract, category, skills, perks), a page per role with the full posting and the quoted facts, and a page per company. Only roles still open and posted in the last 60 days are listed.

| Endpoint | What |
|---|---|
| [`/api/jobs.json`](https://vishstack01.github.io/careeros/api/jobs.json) | 100 roles per page, newest first; `links.next` points to `api/jobs/page-2.json` |
| [`/feed.xml`](https://vishstack01.github.io/careeros/feed.xml) | RSS of the 100 newest roles |
| `/data/jobs/<id>.json` | One role with its full text and facts |

Build it yourself with `careeros site --feed feed --out site`. When a `website/` folder is present, the site's home page is the project website and the board lives at `jobs.html`.

## Auto-apply

The dashboard has an **Auto-apply** switch. Fill in your application details and upload your resume on the dashboard, then a scheduled task in the Claude desktop app applies from your computer's browser, where you sign in to job sites yourself:

- roles you press **Auto-apply** on go first, then, with the switch on, roles whose must-have requirements your resume or Career Brain can back up;
- newest and remote-worldwide roles first, up to your daily cap;
- every field comes from your saved details; short "why us" answers use one real proof point; a tailored resume once your Career Brain is built;
- it stops and lists the role under **Auto-apply needs you** with the exact reason for a sign-in, captcha, one-time code, assessment or any answer it would have to guess.

It never stores passwords, Aadhaar, PAN, bank details, passport or date of birth, and never applies through LinkedIn, Naukri, Indeed or Wellfound. The run's instructions: [prompts/scheduled-apply.md](prompts/scheduled-apply.md).

## Launch it as a product

CareerOS Cloud is the hosted version people sign up for, on the web, as an installable app, or as the Android and iOS apps in [`mobile/`](mobile/). It has Free and Pro plans with Razorpay subscriptions, a monthly AI allowance on your model (or the user's own key, encrypted), and pricing, terms, privacy and refund pages. **[docs/launch.md](docs/launch.md)** walks through every account and setting, from Render to the app stores.

| Free | Pro |
|---|---|
| Fresh roles matched daily, with quotes | Matching every hour |
| 15 AI actions a month, unlimited with your own key | 400 AI actions a month |
| Auto-apply up to 5 a day | Auto-apply up to 25 a day |

## CareerOS Cloud: for many job seekers

The same product as a multi-user service: people sign up with their email, set their filters, upload their resume and get matched against the shared hourly inventory, each with a private pipeline. Auto-apply still runs on each person's own computer, in the Claude desktop app, with a computer key that can only read their pipeline and report results; the server never fills employer forms or holds job-site logins.

- Accounts with email verification, password reset, sign-out everywhere, export and self-service deletion
- PostgreSQL with versioned migrations, a worker with a durable task queue, fail-closed feed ingestion
- Deploy with Docker Compose (HTTPS through Caddy) or the Render blueprint

```bash
pip install -e ".[cloud]"
careeros cloud serve      # http://127.0.0.1:8000, SQLite, emails printed to the terminal
careeros cloud worker     # ingests the feed and matches every account
```

Architecture, deployment and operations: **[docs/cloud.md](docs/cloud.md)**. Before inviting anyone: **[the release checklist](docs/cloud-release-checklist.md)**.

## What it does

| Stage | What happens | How |
|---|---|---|
| Brain | Interviews you and turns your career into claims with evidence | `career-brain` skill, `careeros brain-check` |
| Discover | Scans ~2,000 career pages and 9 remote boards every hour, sweeps ~20,000 more startup boards (open ats-scrapers inventory) for developer roles open to India, adds companies the hiring radar sees on Indeed and Naukri (via JobSpy), reads published pay ranges (Ashby, Lever, Greenhouse) and tags roles that state 20 LPA+; the agent covers the rest of the 96 platforms | `careeros discover`, `deep`, `radar`, `scan`, `filter-feed`, `job-scout` skill |
| Gate | Role, seniority, experience, freshness, open, location, pay, dealbreakers, company; each with a quote | `careeros/gates.py` |
| Check | Still open? A real opening? Re-listed? Work authorization you can meet? | `careeros liveness`, `careeros/signals.py` |
| Research | Company brief, the three problems the team needs solved | `company-research` skill |
| Score | 1–5 against your brain with evidence per requirement, gaps, confidence and a verdict; 4.0 is the apply line | `evaluate` skill, `careeros eval-check` |
| Tailor | Resume where every bullet cites the brain, an ATS-safe PDF checked line by line, cover note, screening answers, keyword coverage, cliché check | `tailor` skill, `careeros claims-check`, `render`, `keywords`, `writing-check` |
| Review | Independent model checks claims, defensibility, 6-second scan, objections | `reviewer` skill |
| Apply | Fills the company's form, submits only when every required answer is covered | `careeros apply`, `apply` skill |
| Outreach | Referral asks to people you already know, hiring-manager, recruiter and LinkedIn notes, follow-ups on day 7 and 14 | `outreach` skill, `careeros warm-intros`, `followups` |
| Track & learn | Inbox sync, funnel, score calibration, skills gap, weekly experiment | `tracker`, `weekly-review` skills, `careeros stats`, `calibrate`, `gaps` |
| Interview & offer | Prep plan, practice, debriefs, red flags, offer-letter walk-through, negotiation brief | `coach` skill, `careeros salary-gap` |

![A role's package with its checks](docs/assets/dashboard-package.png)

## Agent skills

Open the folder in Claude Code and say *"Use the career-brain skill"* with your resume attached. The full walkthrough, including Codex, Antigravity, cron and a fully hosted setup on claude.ai, is in **[docs/build-your-own.md](docs/build-your-own.md)**.

Try the gates on any posting:

```bash
careeros evaluate --company "Demo Co" --title "Junior AI Engineer" --location "Remote, India" \
  --mode remote --text-file posting.txt
```

## Architecture

```mermaid
flowchart LR
  ATS["1,400 career pages<br/>+ remote boards"] --> Scan["scan<br/>(GitHub Actions)"] --> Feed[("feed")] --> Gates["gates + quotes"] --> Store[("store")]
  Boards["96 platforms"] --> Agent["job-scout skill"] --> Gates
  Brain[("Career Brain")] --> Tailor["tailor"]
  Store --> Research["research"] --> Tailor --> Claims["claims-check"] --> Review["reviewer<br/>(second model)"]
  Review --> Apply{"every answer<br/>covered?"}
  Apply -- yes --> Submit["apply + receipt"]
  Apply -- no --> You["your batch"]
  Store --> Dash["dashboard"]
  LLM["your model<br/>(bring your own key)"] -.-> Research & Tailor & Dash
```

Code handles everything with a right answer (dates, experience parsing, dedupe, refusing a second submit); agents handle judgement (interviewing, research, writing, review). Details: **[docs/architecture.md](docs/architecture.md)**.

## Repository map

```
careeros/            Python package (standard library only; Playwright optional)
  sources/           8 hiring-system scouts and 9 remote-board feeds
  discover.py        find each company's job board
  scan.py, feed.py   build the India feed; apply your filters to it
  platforms.py       the job-platform registry and per-run rotation
  extract.py         experience, work mode, remote scope, pay, dates
  gates.py           the gatekeeper
  store.py           SQLite docs, dedupe keys, submit state machine, audit log
  claims.py          resume truth gate, and the same check on the PDF
  signals.py, liveness.py  real-opening signals, re-listing, work authorization, still open?
  evaluation.py      the 1-5 score and its rules
  render.py, jd.py   ATS-safe PDFs; posting archive
  keywords.py, writing.py  keyword coverage; cliché check
  followups.py, replies.py, analytics.py, connections.py  tracking and warm intros
  salary_gap.py, funded.py, doctor.py
  apply/answers.py   form-answer resolver with confidence
  apply/runner.py    Playwright form filler
  site.py, tags.py   the public job board and its tags
  cloud/             the multi-user service: API, worker, plans and billing, migrations, pages
  llm.py             bring-your-own-key client: Anthropic, OpenAI-compatible, Gemini, Ollama
  ai.py              AI steps (profile, posting, evaluate) with code checks on every output
  server.py, cli.py  local dashboard API and command line
.claude/skills/      agent skills: career-brain, job-scout, company-research, evaluate,
                     tailor, reviewer, apply, outreach, tracker, coach, weekly-review
dashboard/           app.html (single source), demo data, built index.html
website/             the project website and docs (GitHub Pages)
mobile/              Android and iOS apps (Capacitor) around the hosted app
prompts/             scheduled search and apply prompts
config/companies/    the company list (curated + moreThanFAANGM + YC), 1,396 companies
config/platforms.toml  96 job platforms with access and competition
config/, brain/      example settings, watchlist, profile and brain
examples/            a tailored resume, an application package, a posting and its evaluation
docs/                architecture, how it works, accuracy, apply agent, data model, guides
tests/               292 tests, including real browser form fills, every LLM provider
                     (mocked), and the cloud service on SQLite and PostgreSQL
```

## Docs

- [How it works, step by step](docs/how-it-works.md)
- [The India feed: 1,400 career pages](docs/feed.md)
- [Job platforms](docs/platforms.md)
- [Architecture](docs/architecture.md)
- [What makes it accurate](docs/accuracy.md)
- [Scoring, documents, tracking and interviews](docs/features.md) (ideas from career-ops)
- [Where the jobs come from, and the open-source projects we evaluated](docs/sources.md)
- [The apply agent](docs/apply-agent.md)
- [Data model](docs/data-model.md)
- [CareerOS Cloud (multi-user)](docs/cloud.md) and its [release checklist](docs/cloud-release-checklist.md)
- [Build your own](docs/build-your-own.md)
- [Launch it as a product](docs/launch.md)
- [Bring your own key](https://vishstack01.github.io/careeros/docs.html#key)
- [Responsible use](docs/responsible-use.md)
- [Roadmap](docs/roadmap.md)
- [AGENTS.md](AGENTS.md): instructions for Claude Code, Codex and Antigravity

## Contributing

Issues and pull requests are welcome: read [CONTRIBUTING.md](CONTRIBUTING.md), the [code of conduct](CODE_OF_CONDUCT.md) and the [security policy](SECURITY.md). Changes are listed in the [changelog](CHANGELOG.md); what's next is on the [roadmap](docs/roadmap.md).

## Responsible use

It never invents experience or fakes a shortlist percentage, never automates LinkedIn, Naukri, Indeed or Wellfound, never handles passwords or captchas, and keeps your data in git-ignored files on your machine. Read [docs/responsible-use.md](docs/responsible-use.md) before you schedule it.

## License

MIT. Built by [Venkata Vishnu Vardhan Raju Chakravarthula](https://github.com/VishStack01) with Claude. The scoring, posting checks, follow-up cadence and interview modes adapt ideas from [career-ops](https://github.com/career-ops-hq/career-ops) (MIT); see [docs/features.md](docs/features.md).
