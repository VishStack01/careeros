# Changelog

All notable changes to CareerOS. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses [semantic versioning](https://semver.org/).

## [1.4.0] - 2026-11-14

### Changed
- **New look across Propelo**: the website, docs, job board, dashboard and app, sign-in, pricing and legal pages, offline screen and extension popup now share one design. It is cream and ink with one pink accent (`#FF85BA`), Figtree at weights 400 to 600, sentence-case labels and fully round buttons. Colour lives in a few moments: the role card with its fit score, the five principle notes, the best-fit card and the four Home tiles, drawn like notes on a board with an ink outline. The pass followed [unslop](https://github.com/heydamir/unslop) (CC BY 4.0); the rules are in [docs/design.md](docs/design.md).
- **Website rebuilt**: a role card with quoted checks in the hero, live numbers from the latest scan, the principles as notes, a dashboard preview, the app on two phones, pricing and a clean footer with link columns. On phones the links fold into a menu.
- **Motion**: the home page opens with the wordmark on pink, which lifts away with a curved edge (once per visit). Headlines arrive letter by letter and a highlighter stroke draws under the key phrase; panels open from the bottom with a curved edge; the source bars fill and the step line follows the scroll. The hero's dot grid reacts to the cursor. Nothing loops, and Reduce Motion shows every page at rest.
- **Brand**: the logo is the word `propelo` with a pink dot. The app, extension and phone icons are a lowercase `p` on a pink tile, and the phone app's splash is the wordmark.
- The role sheet in the dashboard takes its stage colour as pastel paper with ink text.
- Illustrations are removed for now; the prompts stay in [docs/illustrations.md](docs/illustrations.md) for later.

### Added
- `careeros site` writes `data/stats.json` (openings, companies, boards, re-listed roles and the share of each hiring system) so the website shows live numbers.

### Fixed
- Opening a role's package in the dashboard failed with an error before the sheet appeared.
- The sign-in, pricing and legal pages still said "careeros" in their logo.
- On phones, a role's pay and age on the job board could push the page sideways.

## [1.3.0] - 2026-11-11

### Changed
- **CareerOS is now Propelo** (propelo.in). The `propelo` command works alongside `careeros`, which stays for existing scripts. The repository, Python package and data folders keep their names, so nothing you have set up breaks.
- **A calmer, warmer design** on the job board, dashboard and website, following [unslop](https://github.com/heydamir/unslop) (CC BY 4.0): warm paper and ink colours with one pink accent, IBM Plex Mono for dates, figures and sources, three corner sizes, sentence-case labels and one easing curve. Dark mode has its own warm tokens.

### Added
- **Company logos on every role** of the public board. The site build finds each company's own website from evidence (its careers page, the posting itself, or a guessed domain whose homepage names the company), fetches its icon, caches it for 30 days and publishes it with the board. A company without a verified logo shows its initial instead; a wrong logo is never guessed into place.
- **Board**:
  - **Plain-English search**: "remote python internships in Bengaluru over 6 LPA" sets the filters for you, and shows what it understood with a way to undo each part.
  - **Save and hide** roles on the board (kept in your browser), with a Saved list.
  - **Where every role came from**: each card and posting says which board it was found on and when it was last checked, and the posting has "Report a problem".
- **Applications**:
  - new stages: **Assessment** (between Applied and Screen) and **No response** (closed without a reply);
  - **CSV export and import** of your applications, for a spreadsheet or another tracker.
- **Writing & interviews**:
  - six more emails: ask to reschedule an interview, ask for more time on an assessment, questions about an offer, negotiate an offer, accept an offer, withdraw an application;
  - mock interviews by round (campus or fresher, software engineering, AI and data, product and design, managerial, HR) and difficulty (warm-up, standard, tough);
  - **Saved answers**: keep your answers to common application questions, for any company or one company;
  - **Career wins**: a running list of what you did and what changed because of it, used as evidence when Claude writes for you.
- **Campus details** in your application details: CGPA or percentage, branch, active backlogs (only if a form asks, "Prefer not to say" by default), state and PIN code.
- **Job alerts by email** (Propelo Cloud): off by default; daily or weekly in Settings. Each email lists up to ten new roles that passed your filters, best fit first, each with the company's own link, and nothing is sent when there's nothing new.
- **Propelo Autofill 1.3.0**: fills the campus fields, and fills a question from your saved answers when the wording matches closely (a company's own answer is only used for that company). Backlogs are left empty unless you chose an answer.
- **Website**: a new hero with a notice-style role card, and four illustration slots that stay hidden until the images exist. [docs/illustrations.md](docs/illustrations.md) has the prompts, sizes and palette to generate them.
- Home leads with the best fit waiting for you and one line each for fresh roles, applications, replies, interviews in the next two weeks, follow-ups due and skipped roles, each a tap from its page.

### Fixed
- A question such as "Please state your reasons..." is no longer mistaken for the State field.
- Plain-English searches for internships no longer drop every internship by also setting a level.

## [1.2.0] - 2026-11-11

### Added
- **CareerOS Autofill, a Chrome extension** (`extension/`). Press "Fill this form" on a company application page:
  - fills empty fields from your application details and attaches your resume PDF;
  - outlines what it filled in pink and lists what needs you (essays, consent boxes, anything it couldn't match);
  - "Track this application" adds the role to Applications, or updates it if CareerOS already found it (`POST /api/agent/track`).
  - It never submits, never ticks consent boxes, never overwrites what you typed, never fills passwords, codes, identity numbers, bank details or dates of birth, skips voluntary questions and other people's details, and doesn't run on LinkedIn, Naukri, Indeed or Wellfound.
  - It connects with the same computer key as auto-apply and only runs when you press its button, in the tab you're on. A workflow packages it as a zip.
- **Resume score** on every application and posting: how much of the posting's language your resume covers, with matched and missing keywords. Missing keywords are never added for you.
- **Line-by-line review of AI edits**: keep each tailored line, or switch it back to your own (one by one, or all at once).
- **Job families** on the public board and in Settings: Software Engineering, AI & Data, Product & Design, Marketing & Growth, Sales & Accounts, Finance & Strategy, Operations & People. The board adds quick lists (internships, new grads, remote, 20 LPA and up, posted in the last day) and shareable links. Choosing families in Settings matches whole families instead of a keyword list.
- The search now keeps business roles (marketing, sales, finance, operations, people) as well as tech roles.
- **Writing & interviews**: cover letters, five kinds of emails (follow-up, thank-you, referral request, note to a hiring manager, reply to a recruiter), answers to application questions with a word limit, and a mock interview with feedback on each answer. All of it is written only from your profile, with unknown numbers flagged. Templates and a question bank work without AI.

### Fixed
- Solid buttons kept their colour on hover (the text used to disappear).
- An unescaped apostrophe in an AI error message no longer stops the dashboard loading.

## [1.1.1] - 2026-11-05

### Changed
- **Unslopped the website, dashboard, phone app and sign-in pages** with the Appllama app design skill. The rules are written down in [docs/design.md](docs/design.md):
  - one accent (pink) and one warm grey family; the stray saturated blues, violets and teals are gone;
  - a single corner-radius scale;
  - one label per intent;
  - a dark theme on every page.
- **Motion has one vocabulary:** strong ease-out, 280 ms entrances, 190 ms exits, 120 ms presses. Every entrance plays once, from opacity and a short rise, never from `scale(0)` or blur.
- **Decorative motion deleted:** floating and spinning shapes, the infinite marquee, word-by-word headlines, count-ups, parallax, the tilt card and the typing terminal. Tabs change instantly, and lists animate only when a filter changes them.
- **The "Add..." sheet** grows from the "+", and its backdrop fades with it.
- **Back closes before it leaves:** sheets, the job sheet and application pages each own one history entry. Signing in, signing up and confirming your email can't be stepped back into.
- **Home has designed states:**
  - a skeleton shaped like the page while loading;
  - a three-step first-run state before the first match;
  - every touch target at least 44 px, muted text at 4.9:1 contrast, and the toast lifted above the dock.
- **Pricing** is rendered on the server, so it never shows a loading state.

## [1.1.0] - 2026-11-04

### Added
- **A product you can launch.** Free and Pro plans with Razorpay subscriptions (hosted checkout, verified and idempotent webhooks, cancel at the end of the cycle), operator grants for beta testers, and plan-based limits: matching every hour on Pro and daily on Free, AI actions per month, auto-apply per day and storage.
- **AI in the hosted app.** `/api/ai` runs dashboard AI actions on the service's model within the plan's monthly allowance, or on the user's own Anthropic, OpenAI-compatible or Gemini key, stored encrypted. OpenAI-compatible addresses are limited to known providers.
- **New design for the dashboard and the app**, matching the website: black sidebar on wide screens; on phones, a home with one big number and today's highlights as shapes, a floating dock with a pink "+" and an "Add..." sheet, and coloured detail screens.
- **Installable web app** (manifest, service worker, icons, an offline screen) and **Android and iOS apps** in `mobile/` (Capacitor), with a workflow that builds the Android app.
- Sign-in, pricing and policy pages (terms, privacy, refunds, contact) in the brand; pricing and app sections on the website; `docs/launch.md`.

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
