# Job platforms

Generated from [`config/platforms.toml`](../config/platforms.toml) by `scripts/render_platforms.py`. Edit the TOML, not this page.

**96 platforms**, 50 of them low-competition. 11 have public feeds and are scanned automatically every 3 hours; 62 are read by the agent in rotation (every-run ones each time, the rest every third run); 14 need your login, so the agent finds and prepares and you submit; 6 big boards are covered by their own email alerts only.

Why not 300-500? Past about a hundred, "job sites" are mostly clones and scrapers re-posting the same listings (often stale), or sites that only show jobs after login. They add duplicates, not openings. The real reach is the ~1,000 company career pages in [`config/companies/`](../config/companies/), read straight from each company's hiring system.

`verify = true` marks URL patterns not yet confirmed; the first agent run checks them and reports any that moved.

## Remote job boards (20)

| Platform | Region | Competition | How | Notes |
|---|---|---|---|---|
| Remote OK<br>[remoteok.com](https://remoteok.com) | global-remote | high | Scanned (public feed) · every run | JSON API at /api. Their terms ask for a link back to the listing, which the dashboard keeps. |
| Remotive<br>[remotive.com/remote-jobs](https://remotive.com/remote-jobs) | global-remote | medium | Scanned (public feed) · every run | API at /api/remote-jobs. They ask for at most ~4 calls a day; the scan reuses results for 6 hours. |
| Himalayas<br>[himalayas.app/jobs](https://himalayas.app/jobs) | global-remote | medium | Scanned (public feed) · every run | API at /jobs/api. Lists country restrictions per role, so India eligibility is explicit. |
| Jobicy<br>[jobicy.com](https://jobicy.com) | global-remote | low | Scanned (public feed) · every run | API at /api/v2/remote-jobs; has APAC and India geo tags. |
| Working Nomads<br>[www.workingnomads.com/jobs](https://www.workingnomads.com/jobs) | global-remote | low | Scanned (public feed) · every run | API at /api/exposed_jobs/. |
| We Work Remotely<br>[weworkremotely.com](https://weworkremotely.com) | global-remote | high | Scanned (public feed) · every run | RSS. Region field says 'Anywhere in the World' or 'USA Only'. |
| Arbeitnow<br>[www.arbeitnow.com](https://www.arbeitnow.com) | global-remote | low | Scanned (public feed) · every run | API at /api/job-board-api; only its remote roles are kept. Mostly Europe; the location gate drops EU-only roles. |
| Remote Rocketship<br>[www.remoterocketship.com](https://www.remoterocketship.com) | global-remote | low | Agent reads it · every run | Pulls from company ATS pages; filter by 'India' or 'Worldwide' and entry/junior level. |
| aijobs.net<br>[aijobs.net](https://aijobs.net) | global | low | Agent reads it · every run | AI/ML/data only. Filter by India and remote. |
| DailyRemote<br>[dailyremote.com](https://dailyremote.com) | global-remote | medium | Agent reads it | Filter location 'Worldwide' or 'India'. |
| Remote.co<br>[remote.co/remote-jobs](https://remote.co/remote-jobs/) | global-remote | medium | Agent reads it |  |
| JustRemote<br>[justremote.co](https://justremote.co) | global-remote | medium | Agent reads it |  |
| NoDesk<br>[nodesk.co/remote-jobs](https://nodesk.co/remote-jobs/) | global-remote | low | Agent reads it |  |
| Jobspresso<br>[jobspresso.co](https://jobspresso.co) | global-remote | low | Agent reads it |  |
| Remote First Jobs<br>[remotefirstjobs.com](https://remotefirstjobs.com) | global-remote | low | Agent reads it |  |
| 4 Day Week<br>[4dayweek.io/remote-jobs](https://4dayweek.io/remote-jobs) | global-remote | low | Agent reads it |  |
| Pangian<br>[pangian.com/job-travel-remote](https://pangian.com/job-travel-remote/) | global-remote | low | Agent reads it |  |
| Remote Python<br>[www.remotepython.com/jobs](https://www.remotepython.com/jobs/) | global-remote | low | Agent reads it | Python only. |
| web3.career<br>[web3.career](https://web3.career) | global-remote | medium | Agent reads it | Crypto/web3. Has an India filter; many roles are worldwide. |
| CryptoJobsList<br>[cryptojobslist.com](https://cryptojobslist.com) | global-remote | medium | Agent reads it |  |

## Communities (6)

| Platform | Region | Competition | How | Notes |
|---|---|---|---|---|
| Hacker News jobs (YC companies)<br>[news.ycombinator.com/jobs](https://news.ycombinator.com/jobs) | global | low | Scanned (public feed) · every run | Official HN API. YC startups post here directly; few applicants. |
| HN: Who is hiring? (monthly)<br>[news.ycombinator.com/submitted?id=whoishiring](https://news.ycombinator.com/submitted?id=whoishiring) | global | low | Scanned (public feed) · every run | Algolia HN API. ~400 companies a month, many founders reading replies themselves. Many say 'REMOTE (worldwide)'. |
| Python.org job board<br>[www.python.org/jobs](https://www.python.org/jobs/) | global | low | Agent reads it |  |
| Peerlist<br>[peerlist.io/jobs](https://peerlist.io/jobs) | india | low | Agent reads it · every run | Indian builder community; many roles posted by founders and engineers. |
| Hasjob<br>[hasjob.co](https://hasjob.co) | india | low | Agent reads it | HasGeek's board. Low volume now, but almost no competition. |
| r/developersIndia hiring threads<br>[www.reddit.com/r/developersIndia](https://www.reddit.com/r/developersIndia/) | india | low | Agent reads it | Monthly hiring threads and 'we are hiring' posts by engineers. |

## Aggregators that index company pages (7)

| Platform | Region | Competition | How | Notes |
|---|---|---|---|---|
| Hiring Cafe<br>[hiring.cafe](https://hiring.cafe) | global | low | Agent reads it · every run | Indexes company career pages directly (no reposts). Filter India + remote + 0-2 years. |
| EchoJobs<br>[echojobs.io](https://echojobs.io) | global | low | Agent reads it | Tech roles straight from company ATS boards; has Bengaluru and remote filters. |
| startup.jobs<br>[startup.jobs](https://startup.jobs) | global | medium | Agent reads it | Filter remote + India. |
| Levels.fyi jobs<br>[www.levels.fyi/jobs](https://www.levels.fyi/jobs) | global | medium | Agent reads it | Shows pay bands; filter Bengaluru/Hyderabad/Chennai and remote. |
| Adzuna API (India)<br>[developer.adzuna.com](https://developer.adzuna.com) | india | medium | Planned (needs a free API key) | Free app_id/app_key. Set ADZUNA_APP_ID and ADZUNA_APP_KEY as GitHub secrets to include it in the scan (planned). |
| Jooble API<br>[jooble.org/api/about](https://jooble.org/api/about) | india | medium | Planned (needs a free API key) | Free key; planned scan source. |
| Careerjet API<br>[www.careerjet.co.in](https://www.careerjet.co.in) | india | medium | Planned (needs a free API key) | Affiliate key; planned scan source. |

## VC portfolio job boards (26)

| Platform | Region | Competition | How | Notes |
|---|---|---|---|---|
| Y Combinator jobs<br>[www.ycombinator.com/jobs](https://www.ycombinator.com/jobs) | global | medium | Agent reads it · every run | Public listings; filter 'India' and 'Remote'. Applying goes through Work at a Startup. |
| Work at a Startup (YC)<br>[www.workatastartup.com](https://www.workatastartup.com) | global | medium | You apply (login) | One YC profile reaches every YC company; founders message you. |
| Peak XV Partners portfolio jobs<br>[careers.peakxv.com/jobs](https://careers.peakxv.com/jobs) | india | low | Agent reads it · every run · to verify |  |
| Accel India portfolio jobs<br>[jobs.accel.com/jobs](https://jobs.accel.com/jobs) | india | low | Agent reads it · every run · to verify |  |
| Lightspeed portfolio jobs<br>[jobs.lsvp.com/jobs](https://jobs.lsvp.com/jobs) | global | low | Agent reads it · to verify |  |
| Elevation Capital portfolio jobs<br>[jobs.elevationcapital.com/jobs](https://jobs.elevationcapital.com/jobs) | india | low | Agent reads it · to verify |  |
| Blume Ventures portfolio jobs<br>[jobs.blume.vc/jobs](https://jobs.blume.vc/jobs) | india | low | Agent reads it · to verify |  |
| Nexus Venture Partners portfolio jobs<br>[jobs.nexusvp.com/jobs](https://jobs.nexusvp.com/jobs) | india | low | Agent reads it · to verify |  |
| Z47 (formerly Matrix Partners India) portfolio jobs<br>[jobs.z47.com/jobs](https://jobs.z47.com/jobs) | india | low | Agent reads it · to verify |  |
| Together Fund portfolio jobs<br>[jobs.together.fund/jobs](https://jobs.together.fund/jobs) | india | low | Agent reads it · to verify | India-founded SaaS and AI companies, many remote-first. |
| Kalaari Capital portfolio jobs<br>[jobs.kalaari.com/jobs](https://jobs.kalaari.com/jobs) | india | low | Agent reads it · to verify |  |
| Chiratae Ventures portfolio jobs<br>[jobs.chiratae.com/jobs](https://jobs.chiratae.com/jobs) | india | low | Agent reads it · to verify |  |
| 3one4 Capital portfolio jobs<br>[jobs.3one4capital.com/jobs](https://jobs.3one4capital.com/jobs) | india | low | Agent reads it · to verify |  |
| Stellaris Venture Partners portfolio jobs<br>[jobs.stellarisvp.com/jobs](https://jobs.stellarisvp.com/jobs) | india | low | Agent reads it · to verify |  |
| Prime Venture Partners portfolio jobs<br>[jobs.primevp.in/jobs](https://jobs.primevp.in/jobs) | india | low | Agent reads it · to verify |  |
| India Quotient portfolio jobs<br>[jobs.indiaquotient.in/jobs](https://jobs.indiaquotient.in/jobs) | india | low | Agent reads it · to verify |  |
| Antler India portfolio jobs<br>[careers.antler.co/jobs](https://careers.antler.co/jobs) | global | low | Agent reads it · to verify |  |
| Venture Highway portfolio jobs<br>[jobs.venturehighway.vc/jobs](https://jobs.venturehighway.vc/jobs) | india | low | Agent reads it · to verify |  |
| Bessemer India portfolio jobs<br>[jobs.bvp.com/jobs](https://jobs.bvp.com/jobs) | global | low | Agent reads it · to verify |  |
| a16z portfolio jobs<br>[jobs.a16z.com/jobs](https://jobs.a16z.com/jobs) | global | medium | Agent reads it · to verify |  |
| Sequoia portfolio jobs<br>[jobs.sequoiacap.com/jobs](https://jobs.sequoiacap.com/jobs) | global | medium | Agent reads it · to verify |  |
| General Catalyst portfolio jobs<br>[jobs.generalcatalyst.com/jobs](https://jobs.generalcatalyst.com/jobs) | global | medium | Agent reads it · to verify |  |
| Index Ventures startup jobs<br>[www.indexventures.com/startup-jobs](https://www.indexventures.com/startup-jobs) | global | medium | Agent reads it · to verify |  |
| Greylock portfolio jobs<br>[jobs.greylock.com/jobs](https://jobs.greylock.com/jobs) | global | medium | Agent reads it · to verify |  |
| Khosla Ventures portfolio jobs<br>[jobs.khoslaventures.com/jobs](https://jobs.khoslaventures.com/jobs) | global | medium | Agent reads it · to verify |  |
| Insight Partners portfolio jobs<br>[jobs.insightpartners.com/jobs](https://jobs.insightpartners.com/jobs) | global | medium | Agent reads it · to verify |  |

## Indian startup boards (6)

| Platform | Region | Competition | How | Notes |
|---|---|---|---|---|
| Wellfound (AngelList Talent)<br>[wellfound.com/jobs](https://wellfound.com/jobs) | global | high | You apply (login) | Strong India startup coverage. Blocks automated access; the agent links roles, you apply. |
| Weekday<br>[www.weekday.works](https://www.weekday.works) | india | low | Agent reads it · every run | Indian startup roles with salary bands; many not posted elsewhere. |
| Cutshort<br>[cutshort.io/jobs](https://cutshort.io/jobs) | india | medium | You apply (login) | Tech startup roles; AI matching. Public pages show role details. |
| Instahyre<br>[www.instahyre.com](https://www.instahyre.com) | india | medium | You apply (login) | Recruiters reach out; keep the profile current. |
| Hirist<br>[www.hirist.tech](https://www.hirist.tech) | india | medium | You apply (login) |  |
| TechGig jobs<br>[www.techgig.com/jobs](https://www.techgig.com/jobs) | india | medium | Agent reads it |  |

## Fresher-first (7)

| Platform | Region | Competition | How | Notes |
|---|---|---|---|---|
| GeeksforGeeks jobs<br>[www.geeksforgeeks.org/jobs](https://www.geeksforgeeks.org/jobs) | india | medium | Agent reads it | Many fresher and 0-2 year roles. |
| HackerEarth jobs and hiring challenges<br>[www.hackerearth.com/challenges/hiring](https://www.hackerearth.com/challenges/hiring/) | india | medium | You apply (login) | Hiring challenges skip the resume screen. |
| Unstop<br>[unstop.com/jobs](https://unstop.com/jobs) | india | medium | You apply (login) · every run | Fresher jobs and hiring competitions. |
| Internshala jobs<br>[internshala.com/jobs](https://internshala.com/jobs/) | india | high | You apply (login) | Fresher jobs (filter 7 LPA+) and internships. |
| Cuvette<br>[cuvette.tech](https://cuvette.tech) | india | medium | You apply (login) |  |
| Talentd<br>[www.talentd.in](https://www.talentd.in) | india | medium | Agent reads it | Fresher and off-campus tech roles; links to company pages. |
| Freshersworld<br>[www.freshersworld.com](https://www.freshersworld.com) | india | high | Agent reads it |  |

## Talent marketplaces (3)

| Platform | Region | Competition | How | Notes |
|---|---|---|---|---|
| Arc<br>[arc.dev/remote-jobs](https://arc.dev/remote-jobs) | global-remote | medium | You apply (login) | Remote roles open to India; profile vetting first. |
| Uplers<br>[www.uplers.com](https://www.uplers.com) | india | medium | You apply (login) | Remote roles at global companies for Indian engineers; vetting first. |
| Turing<br>[www.turing.com/jobs](https://www.turing.com/jobs) | global-remote | medium | You apply (login) |  |

## AI work marketplaces (2)

| Platform | Region | Competition | How | Notes |
|---|---|---|---|---|
| Mercor<br>[work.mercor.com](https://work.mercor.com) | global-remote | medium | You apply (login) | AI-lab contract roles (evaluation, data, engineering); AI interview once, then many roles. |
| micro1<br>[www.micro1.ai/jobs](https://www.micro1.ai/jobs) | global-remote | medium | You apply (login) |  |

## X-ray searches (11)

| Platform | Region | Competition | How | Notes |
|---|---|---|---|---|
| X-ray: Lever boards in India<br>`site:jobs.lever.co (Bengaluru OR Bangalore OR Hyderabad OR Chennai OR "Remote - India")` | india | low | Agent reads it · every run |  |
| X-ray: Greenhouse boards in India<br>`(site:boards.greenhouse.io OR site:job-boards.greenhouse.io) (Bengaluru OR Hyderabad OR Chennai OR "Remote India")` | india | low | Agent reads it · every run |  |
| X-ray: Ashby boards in India<br>`site:jobs.ashbyhq.com (India OR Bengaluru OR Hyderabad OR Chennai)` | india | low | Agent reads it · every run |  |
| X-ray: Workable boards in India<br>`site:apply.workable.com (Bengaluru OR Hyderabad OR Chennai OR Kochi OR Coimbatore)` | india | low | Agent reads it |  |
| X-ray: SmartRecruiters in India<br>`site:jobs.smartrecruiters.com (Bengaluru OR Hyderabad OR Chennai) engineer` | india | low | Agent reads it |  |
| X-ray: Keka career pages<br>`site:keka.com/careers (engineer OR developer OR "data")` | india | low | Agent reads it | Keka is used by many Indian startups that never post on job boards. |
| X-ray: Zoho Recruit career pages<br>`site:zohorecruit.in (engineer OR developer)` | india | low | Agent reads it |  |
| X-ray: Darwinbox career pages<br>`site:darwinbox.in careers (engineer OR developer)` | india | low | Agent reads it |  |
| X-ray: Freshteam career pages<br>`site:freshteam.com/jobs (engineer OR developer)` | india | low | Agent reads it |  |
| X-ray: 'remote, open to India'<br>`"remote" ("open to candidates in India" OR "anywhere in the world" OR "worldwide") ("AI engineer" OR "software engineer") -senior` | global-remote | low | Agent reads it · every run |  |
| X-ray: founders hiring on LinkedIn posts<br>`site:linkedin.com/posts ("we are hiring" OR "we're hiring") (Bengaluru OR Hyderabad OR Chennai OR remote) (AI OR "software engineer") fresher` | india | low | Agent reads it | Read-only via search results. The agent never logs into LinkedIn; it drafts the reply for you to send. |

## Big boards (email alerts only) (6)

| Platform | Region | Competition | How | Notes |
|---|---|---|---|---|
| LinkedIn Jobs<br>[www.linkedin.com/jobs](https://www.linkedin.com/jobs/) | india | high | Email alerts | Set job alerts (past 24 hours, Entry level, your cities + Remote). Automation breaks their terms and risks your account. |
| Naukri<br>[www.naukri.com](https://www.naukri.com) | india | high | Email alerts | Keep the profile updated daily (recruiter search favours fresh profiles); use alerts. |
| Indeed India<br>[in.indeed.com](https://in.indeed.com) | india | high | Email alerts |  |
| foundit (Monster India)<br>[www.foundit.in](https://www.foundit.in) | india | high | Email alerts |  |
| Glassdoor India<br>[www.glassdoor.co.in/Job](https://www.glassdoor.co.in/Job/) | india | high | Email alerts |  |
| Shine<br>[www.shine.com](https://www.shine.com) | india | high | Email alerts |  |

## Company lists (2)

| Platform | Region | Competition | How | Notes |
|---|---|---|---|---|
| Y Combinator company directory<br>[www.ycombinator.com/companies?regions=India](https://www.ycombinator.com/companies?regions=India) | india | low | Scanned (public feed) | Used by scripts/build_company_list.py. |
| remoteintech/remote-jobs<br>[github.com/remoteintech/remote-jobs](https://github.com/remoteintech/remote-jobs) | global-remote | low | Scanned (public feed) | Hundreds of remote-friendly companies; candidates for the company list. |
