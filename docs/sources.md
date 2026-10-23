# Where the jobs come from, and the open-source projects we looked at

## Sources CareerOS reads

| Source | How | Runs |
|---|---|---|
| ~1,400 company career pages (curated list, MoreThanFAANGM, YC India and remote companies) | Each company's own Greenhouse, Lever, Ashby, SmartRecruiters, Recruitee, Breezy, Personio or Workable board, through its public API | Hourly scan on GitHub Actions |
| **Deep sweep** (new): about 20,000 company boards on Ashby, Lever, Greenhouse, Workable, SmartRecruiters and Recruitee, from the open [ats-scrapers](https://github.com/kalil0321/ats-scrapers) inventory (MIT) | `careeros deep` lists the boards CareerOS doesn't know yet; `discover` checks up to 800 an hour and keeps a board only when it lists a developer role in India or open to India (a bare "Remote" doesn't count). The rest are checked again after three weeks | List refreshed daily, checked hourly |
| **High payers' own sites**: Workday (NVIDIA, Salesforce, Adobe, PayPal, Qualcomm, Visa, Walmart Global Tech, Intel, Cisco, Mastercard, Sprinklr and more) and amazon.jobs | Their public job APIs, narrowed to India; Workday through each site's own country filter | Hourly scan |
| **Hiring radar**: companies hiring on Indeed India and Naukri | [JobSpy](https://github.com/speedyapply/JobSpy) (MIT) searches the boards; CareerOS keeps only the employer's own board link or the company name, adds that board to the scan, and reads the roles there | Every third hourly scan |
| 9 remote boards with public feeds: Remote OK, Remotive, Himalayas, Jobicy, Working Nomads, We Work Remotely, Arbeitnow, HN jobs, HN Who is hiring | Their published JSON or RSS, within each board's polling limits | Hourly scan |
| 96 job platforms without an open feed (Wellfound, Cutshort, Instahyre, Hirist, Uplers, VC portfolio boards and more) | The search agent visits a rotating set each run, public pages only | Every 3 hours |
| Funding news (Inc42, Entrackr, TechCrunch India) | Newly funded companies listed for you to add | Hourly scan |

Every role on the board and the dashboard links to the employer's own posting.
Applications go to the employer's site, never to Indeed, Naukri or LinkedIn.

### Pay

Pay comes from the posting itself, never from a guess:

- **Ashby** boards publish a compensation summary and **Lever** boards a salary
  range when the company sets one; the scan reads both.
- **Greenhouse** keeps pay ranges off the job list and serves them per job
  (`pay_transparency=true`). The scan asks once for each developer role in
  India or remote that doesn't state pay in its text (up to 200 new lookups an
  hour) and remembers the answer. Rupee ranges always count; a dollar range
  counts only for a remote role, since it usually describes US hiring.
- Otherwise the posting text is read for a stated salary or CTC.

The board and the dashboard tag a role **20 LPA+** when the top of its stated
range is 20 LPA or more (dollar pay is converted at ₹88 per $). The board can
filter by it and sort by the highest stated pay, and the search puts these roles
first within each region.

**Public pay data for freshers.** Most well-paying employers never print a
salary. `config/pay/entry-pay.csv` lists what about 45 of them are publicly
reported to pay at entry level in India (quant firms, big tech, top product
companies), with sources. A role that doesn't state pay passes your floor on
this data only when the **low** end of the range meets it, and the dashboard
marks it "est.". The posting's own figure always wins.

**Only roles with pay evidence** (Preferences) keeps a role only when its
posting states pay at or above your floor. Most Indian postings don't state pay,
so this shows far fewer roles; the rest stay in the skip log, where *Prepare
anyway* brings one back. With it on, the search agent visits the platforms whose
listings show salaries first (`states_pay = true` in `config/platforms.toml`:
YC jobs, Levels.fyi, Wellfound, Weekday, Cutshort, Uplers, Hiring Cafe, Remote
Rocketship, Internshala and others).

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
| [ats-scrapers](https://github.com/kalil0321/ats-scrapers) (MIT) | Open inventory of ~20,500 company job boards across ATS platforms, plus scrapers | **Yes, as the deep sweep.** Only the company inventory is used; CareerOS reads each board through its own readers. Of 23 well-paying fresher employers we checked that CareerOS wasn't scanning (quant firms, Datadog, Figma, Anthropic, Cursor, Notion, Canva and others), 22 are in it. |
| [clearfetch/ats-jobs-scraper](https://github.com/clearfetch/ats-jobs-scraper) (MIT) | Reads salary from ATS data (Greenhouse pay transparency, Lever, Ashby, Recruitee) | **Same approach, built in.** The scan now reads Greenhouse pay ranges too. |
| [job-board-aggregator](https://github.com/Feashliaa/job-board-aggregator) | 1M+ roles from ~95,000 company boards found through Common Crawl | **No.** Its company lists are CC BY-NC, which doesn't fit an MIT project. The ats-scrapers inventory covers the same boards that matter here. |
| [LastRound AI ATS directory](https://datahub.io/lastroundai-hiring-data/lastroundai-hiring-data) (CC BY 4.0) | ~9,900 companies mapped to their ATS board, plus pay-transparency statistics | **Not yet.** Largely overlaps the ats-scrapers inventory; its statistics confirm that rupee pay is rarely published. |
| [job-radar](https://github.com/ChaitanyaKhanna14/job-radar) | Daily fresher roles in India from ~80 companies that pay 8 LPA+ | **No code used** (no license). It was used only as a check on coverage, which is how the 23 missing employers above were found. |
| [Autofill-Jobs](https://github.com/andrewmillercode/Autofill-Jobs) (MIT) | Browser extension that fills Greenhouse, Lever and Workday forms | **Not needed.** CareerOS fills forms itself in the Claude desktop app's browser, from your profile, and it's unmaintained. Fine to use alongside for manual applications. |
| [Resume-Matcher](https://github.com/srbhr/Resume-Matcher), [resume-lm](https://github.com/olyaiy/resume-lm) | Resume tailoring and keyword match | **Covered** by the `tailor` skill, `careeros keywords` and the claims checker, which refuses invented claims. |
| [250CompanyList](https://github.com/KushalVijay/250CompanyList) | 250 companies paying 15 LPA+ for tech roles in India, with campus CTC | **Used as a pay source** in `config/pay/entry-pay.csv` (cited per row). |
| levels.fyi leaderboards | Highest-paying companies by level and country | **Read by the agent** (Levels.fyi jobs in the platform list); its data isn't redistributed. |
| LinkedIn connections API | Would list a member's connections | **Not available.** LinkedIn restricts it to approved partners; sign-in apps get name, email and photo only. Referrals use your own Connections.csv export and searches you open yourself. |
| Adzuna API | Job search with salary filters, India included | **No, for now.** Its terms don't allow redistributing results without Adzuna's written consent, and the CareerOS feed is public. It could run privately on your own computer later. |
