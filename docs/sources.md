# Where the jobs come from, and the open-source projects we looked at

## Sources CareerOS reads

| Source | How | Runs |
|---|---|---|
| ~1,400 company career pages (curated list, MoreThanFAANGM, YC India and remote companies) | Each company's own Greenhouse, Lever, Ashby, SmartRecruiters, Recruitee, Breezy, Personio or Workable board, through its public API | Hourly scan on GitHub Actions |
| **Hiring radar** (new): companies hiring on Indeed India and Naukri | [JobSpy](https://github.com/speedyapply/JobSpy) (MIT) searches the boards; CareerOS keeps only the employer's own board link or the company name, adds that board to the scan, and reads the roles there | Every third hourly scan |
| 9 remote boards with public feeds: Remote OK, Remotive, Himalayas, Jobicy, Working Nomads, We Work Remotely, Arbeitnow, HN jobs, HN Who is hiring | Their published JSON or RSS, within each board's polling limits | Hourly scan |
| 96 job platforms without an open feed (Wellfound, Cutshort, Instahyre, Hirist, Uplers, VC portfolio boards and more) | The search agent visits a rotating set each run, public pages only | Every 3 hours |
| Funding news (Inc42, Entrackr, TechCrunch India) | Newly funded companies listed for you to add | Hourly scan |

Every role on the board and the dashboard links to the employer's own posting.
Applications go to the employer's site, never to Indeed, Naukri or LinkedIn.

### Pay

The board and the dashboard tag a role **20 LPA+** when the posting itself
states pay of 20 LPA or more at the top of its range (dollar pay is converted at
₹88 per $). The board can filter by it and sort by the highest stated pay, and
the search puts these roles first within each region. Roles that don't state
pay are never guessed into a band.

## Open-source projects we evaluated

| Project | What it does | In CareerOS? |
|---|---|---|
| [JobSpy](https://github.com/speedyapply/JobSpy) (MIT) | Scrapes LinkedIn, Indeed, Glassdoor, Naukri and others | **Yes, as the hiring radar.** Indeed India and Naukri are on by default; LinkedIn and Glassdoor block cloud servers quickly and stay off unless you turn them on in `config/radar.toml`. Their listings are never published, only the employer boards they point to. |
| [career-ops](https://github.com/career-ops-hq/career-ops) (MIT) | Evaluation, posting checks, follow-ups, interview prep | **Yes**, adapted (see [features.md](features.md)). |
| MoreThanFAANGM, YC company lists, [remoteintech](https://github.com/remoteintech/remote-jobs) | Company lists | **Yes**, in the company list the scan maps. |
| [SimplifyJobs New-Grad-Positions](https://github.com/SimplifyJobs/New-Grad-Positions) | A large, well-kept list of new-grad roles | **No.** Of its 917 roles posted in the last 30 days (checked on 23 Oct 2026), none were in India and the 34 remote ones were US-based. |
| LinkedIn auto-appliers ([Auto_job_applier_linkedIn](https://github.com/GodsScion/Auto_job_applier_linkedIn) and similar), Naukri and Indeed apply bots | Sign in as you and mass-apply with Easy Apply | **No.** LinkedIn, Naukri and Indeed restrict accounts that automate applying, and a restricted account costs more than any number of applications. CareerOS applies on the company's own form instead. |
| [Jobs_Applier_AI_Agent_AIHawk](https://github.com/feder-cr/Jobs_Applier_AI_Agent_AIHawk) | Was a LinkedIn auto-applier | **No.** The repository now hosts a different project, a general agent built to evade anti-bot systems. |
| [Skyvern](https://github.com/Skyvern-AI/skyvern) (AGPL-3.0), [browser-use](https://github.com/browser-use/browser-use) (MIT) | General browser agents that can fill forms | **Not needed.** CareerOS already fills forms with Claude in the Claude desktop app's browser, where you're signed in. These would need their own model API keys and hosting. |
| [Resume-Matcher](https://github.com/srbhr/Resume-Matcher) (Apache-2.0) | Resume vs posting keyword analysis | **Covered** by `careeros keywords` (coverage, never an "ATS score"). |
| Adzuna API | Job search with salary filters, India included | **No, for now.** Its terms don't allow redistributing results without Adzuna's written consent, and the CareerOS feed is public. It could run privately on your own computer later. |
