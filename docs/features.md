# Evaluation, documents, tracking and interviews

These features follow ideas from [career-ops](https://github.com/career-ops-hq/career-ops)
(MIT), a job-search system built on Claude Code. The code here is our own; where
a rule or a cadence comes from career-ops, the module says so. What we left out,
and why, is at the end.

## Before you spend time on a posting

| Check | What it does | Where |
|---|---|---|
| Is it still open? | Asks the hiring system's own API first (Greenhouse, Lever, Ashby, SmartRecruiters, Workable), then reads the page for a closure notice or an Apply button. Anything else is "uncertain", never a guess. | `careeros liveness <url>`, `careeros/liveness.py` |
| Is it a real opening? | Observations, not accusations: posting age, a closure notice, re-listing, how specific the posting is, contradictions (an "entry-level" title asking 5 years), whether pay is shown and whether a recruiter posted it for an unnamed client. Three tiers: Looks real, Check before applying, Suspicious. | `careeros/signals.py`, shown on the job board and in the dashboard |
| Re-listed? | The same company and the same title words, posted again after the earlier listing disappeared, within 90 days. Parallel openings don't count. | `RepostHistory` in `careeros/signals.py`; history kept on the feed branch |
| Can you legally take it? | "US citizens only", security clearances and "must be authorized to work in X" rule a role out unless X is India. "No visa sponsorship" doesn't, for remote work from India. | the Work authorization gate in `careeros/gates.py` |
| Role family | Forward deployed, Agentic and automation, AI platform and LLMOps, Solutions architect, AI product, AI transformation, Applied AI and LLM engineering. A filter on the job board. | `careeros/signals.py` |

## Scoring a role (1 to 5, apply line 4.0)

The `evaluate` skill writes one JSON evaluation per role and `careeros eval-check`
checks it before it's saved:

- **Requirements first, from the posting alone**, before the brain is opened, so
  how much a requirement matters is never bent by how well you meet it. Each row
  is `critical`, `high`, `meaningful`, `preferred` or `low_signal`, and `stated`
  (a verbatim quote, checked against the archived posting), `structural` or
  `inferred`. An inferred row can never be critical or high.
- **Matches from the brain**: strong (with the claim id), partial, missing.
  Planned work never counts.
- **Gaps** for every critical or high requirement you only partly meet: the
  interview risk and what to do about it.
- **Five dimensions** (match, fit with the roles you want, pay, company and
  culture, red flags), each with what it rests on.
- **Confidence** is computed, never typed: High only when all five are
  supported and nothing is open. It rates the evidence, not your chances.
- **Verdict**: 4.5+ apply now; 4.0–4.4 worth applying; 3.5–3.9 only for a
  specific reason; under 3.5 don't. **Auto-apply never submits a role under
  4.0** unless you press "Apply anyway"; the cloud server enforces it.
- Also: level strategy, company type and how reliable its pay data is, resume
  changes, stories to prepare, draft answers (4.0+ only) and the posting's keywords.

`careeros eval-check eval.json --jd jd.txt --md report.md` writes the A–H report,
with the posting archived at the end.

## Documents

| | |
|---|---|
| `careeros archive-jd <url>` | Saves the posting's full text verbatim before you apply. Postings disappear before interviews. |
| `careeros render resume.json --out resume.pdf` | An ATS-safe PDF: one column, standard headings, real text, links written out. Refuses a resume that fails the claims check, then reads the PDF back. |
| `careeros pdf-check resume.pdf --resume resume.json` | Blocks a PDF that drops a checked bullet or adds a number your brain, resume or profile doesn't have. |
| `careeros keywords --jd jd.txt --resume resume.json` | Which of the posting's terms appear in your bullets, only in your skills list, or nowhere. A coverage list, never an "ATS score". |
| `careeros writing-check note.txt` | Flags stock openers, unprovable adjectives, jargon and machine-sounding phrases in cover notes, answers and messages. |

## After you apply

| | |
|---|---|
| Follow-ups | Day 7 and day 14 after applying, then stop. A reply to a recruiter within a day. A thank-you the day after each interview. Unsent nudges close themselves when the company replies. `careeros followups` lists what's due. |
| `careeros classify-reply email.txt` | Confirmation, rejection, assessment, recruiter reply, interview or offer, with the sentence that decided it. Unclear emails go to you. |
| `careeros stats` | The funnel, reply rate, time to a reply, time from posting to applying, by region, source and role family. Small samples are labelled. |
| `careeros calibrate` | Do roles scored 4.5+ get more replies than 4.0–4.4 ones? If not, the scoring needs a look. |
| `careeros gaps` | Skills your kept roles keep asking for that your brain can't prove yet. |
| Warm intros | Upload LinkedIn's own Connections.csv on the Outreach tab (or `careeros warm-intros`). Matches are tiered: works there, very likely, or a similar name to check. It stays in your private dashboard. |

## Interviews and offers

The `coach` skill: a prep plan with the process and who you'll meet, practice
questions scored one at a time, a debrief after each round, red flags across
rounds (scope drift against the archived posting, questions an employer
shouldn't ask), an offer-letter walk-through that describes each clause and
lists questions for a lawyer (it is not legal advice), and a negotiation brief
built on `careeros salary-gap`: the posting's range, your floor and ask, every
number you've stated, and the offer.

## Finding companies and checking your setup

- `careeros funded` reads funding news (Inc42, Entrackr, TechCrunch India) and
  lists newly funded companies; nothing is added until you run `--add`. The
  hourly scan also writes `feed/funded.json` for review.
- `careeros doctor` checks Python, your config, the brain, Playwright, the
  database and the kill switch, and fails if any private file is tracked by git.

## What we didn't take, and why

- **A terminal dashboard**: the CareerOS dashboard is a web page that works on
  your phone and in Claude.
- **Plugins and a self-updater**: skills and `git pull` cover it.
- **Translations of every mode**: the product targets India in English first.
- **LaTeX resumes**: HTML to PDF is easier to keep ATS-safe and to check.
- **Scanners for German and Dayforce boards**: outside the India-first scope.
- **Paid batch evaluation runs**: scoring happens inside your own Claude runs.
