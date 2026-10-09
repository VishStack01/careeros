# Build your own

Pick a path. All of them share the same code, skills and data model.

| Path | Best for | Runs where |
|---|---|---|
| A. Local with Claude Code | Most people; full control, data on your machine | Your computer + cron |
| B. Codex | Using Codex as the main agent or as the independent reviewer | Your computer |
| C. Antigravity | Browser-driven applying and editing the dashboard | Your computer |
| D. Hosted on claude.ai | No server; dashboard and schedules in Claude | Claude cloud + your computer for applying |

## Prerequisites
- Python 3.11 or newer, Git
- For applying: Playwright and Chromium (`python -m playwright install chromium`)
- An agent: Claude Code, Codex or Antigravity

## A. Local with Claude Code

```bash
git clone https://github.com/VishStack01/careeros.git
cd careeros
python -m venv .venv && source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -e ".[browser,dev]"
python -m playwright install chromium
python -m pytest -q                                     # everything should pass
careeros init                                           # creates your private config files
```

1. **Brain.** Open Claude Code in the folder and say: *"Use the career-brain skill. Here's my resume."* Attach your resume and LinkedIn PDF. Answer its questions. Finish with `careeros brain-check`.
2. **Profile.** Edit `config/profile.toml`: contact details, education, CTC, notice period, work authorization. Leave out anything you don't want an agent to enter.
3. **Filters.** Edit `config/settings.toml`: experience limit, posting window, locations, pay floor, dealbreakers, companies to avoid.
4. **Watchlist.** Add companies to `config/watchlist.toml`. Their board tokens are in their career-page URLs (`jobs.ashbyhq.com/<token>`, `job-boards.greenhouse.io/<token>`, `jobs.lever.co/<token>`).
5. **First scout.**
   ```bash
   careeros scout
   careeros list --stage found
   careeros show <job-id>
   ```
6. **Dashboard.** `careeros serve`, then open http://127.0.0.1:8765.
7. **Prepare and apply.** In Claude Code: *"Research and prepare the top three found roles"* (company-research → tailor → reviewer). Then dry-run and submit:
   ```bash
   careeros apply "<apply url>" --job-id <id> --package packages/<id>/package.json
   careeros apply "<apply url>" --job-id <id> --package packages/<id>/package.json --submit
   ```
8. **Schedule.** `crontab -e`:
   ```cron
   14 */3 * * *  cd ~/careeros && .venv/bin/careeros scout --schedule "every 3 hours" >> data/scout.log 2>&1
   ```
   Or ask Claude Code to create a scheduled task that runs the `job-scout` skill every 3 hours.

## B. Codex
Codex reads `AGENTS.md`. Use the same commands. The most valuable split is to
draft with Claude and **review with Codex**: run the `reviewer` skill in Codex
on `packages/<id>/` so the checker is a different model from the writer.

## C. Antigravity
Open the folder; Antigravity reads `AGENTS.md`. Use its browser agent for the
`apply` skill on forms that `careeros apply` doesn't handle (Workday, custom
career sites), following the skill's stop rules. Edit `dashboard/app.html` and
rebuild with `python scripts/build_dashboard.py`.

## D. Hosted on claude.ai
1. Publish `dashboard/app.html` as an artifact with the `db` and `user`
   capabilities, readable and writable by the owner only.
2. Seed `settings/profile` and `brain/status` with the ArtifactData tool.
3. Create a scheduled task every 3 hours with `prompts/scheduled-search.md`
   (cloud; no computer needed).
4. Once your brain and profile are ready, create a second scheduled task that
   **requires your computer** with `prompts/scheduled-apply.md`, and sign in to
   the job boards once in the Claude desktop app's browser.

## Extending

**A new ATS source.** Add `careeros/sources/<ats>.py` with `normalize(item, company) -> Job` and `fetch(token, company) -> list[Job]`, register it in `sources/__init__.py`, add a fixture JSON and a test in `tests/test_sources_store.py`.

**A new gate.** Add `gate_<name>(job, settings) -> Check` in `gates.py`, call it from `evaluate`, and add pass and fail cases to `tests/test_gates.py`. Always return the quote that decided it.

**A new form-answer rule.** Add a regex and handler in `answers._rule_based`, and a test in `tests/test_answers.py`. If the answer could be wrong for some people, return `ESCALATE` rather than a guess.
