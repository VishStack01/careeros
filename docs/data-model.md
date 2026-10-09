# Data model

Every record is a JSON document in a collection. The same shapes are used by
the local SQLite store and the hosted artifact database.

## `jobs/<id>`
| Field | Type | Notes |
|---|---|---|
| company, title, url, source | string | `url` is the canonical (company) page when one exists |
| location, workMode | string | workMode: `remote` · `hybrid` · `onsite` · `""` |
| region | string | `remote-global` · `remote-india` · `south-india` (priority order) |
| postedAt, foundAt, applyBy | ISO 8601 / date | |
| priority | bool | posted within `priority_within_hours` |
| salary, experience | string | display text, e.g. `8–10 LPA`, `1+ years` |
| applicants | number | when the board shows it |
| stage | string | `found` `ready` `approved` `applied` `screen` `interview` `offer` `rejected` `withdrawn` `skipped` |
| checks | `[{gate, passed, value, quote}]` | one per gate; `quote` is copied from the posting |
| skip | `{gate, reason, wouldChange}` | for skipped roles |
| brief | `{about, team, whyNow, problems[], stack[], salaryBand, interviewIntel, sources[]}` | company-research |
| decision, decisionReason, fitBand | `A`–`F`, string, `strong`·`good`·`stretch`·`pending` | |
| dimensions | `[{name, level 0–3, reason}]` | fit by dimension, never a percentage |
| evidence, gaps | `[{requirement, evidence, source}]`, `[string]` | evidence map |
| resume, coverNote, screening, knockouts | package fields | |
| outreach | `{contact, email, linkedin, recruiterNote}` | drafts and their sent status |
| followUps | `[{label, due, note, done}]` | |
| appliedAt, appliedVia, screenAt, interviewAt | | |
| timeline | `[{at, event}]` | append-only history |
| notes | string | yours |

## `settings/profile`
Search and display settings: `experienceLevels`, `maxRequiredYears`,
`maxPostingAgeDays`, `locations`, `salaryFloorLpa`, `dailyCap`, `approvalMode`
(`auto-when-clear` · `daily-batch`), `schedule`.

## `brain/status`
`{state: "waiting" | "building" | "ready", summary, counts, missing[], updatedAt}`.
The brain itself (`brain/brain.json`) stays on your machine; see
`brain/brain.example.json` for its schema.

## `runs/<id>`
`{startedAt, finishedAt, scanned, added, skipped, summary, error?}`.

## Files on your machine (git-ignored)
| Path | Contents |
|---|---|
| `config/profile.toml` | Application answers (contact, education, CTC, authorization) |
| `config/settings.toml` | Search filters |
| `config/watchlist.toml` | Company boards to poll |
| `brain/brain.json` | Career Brain |
| `packages/<job-id>/` | `resume.json`, `resume.pdf`, `package.json`, `review.json`, `interview.md` |
| `receipts/<time>-<job-id>/` | `filled.png`, `after-submit.png`, `result.json` |
| `data/careeros.db` | SQLite: `docs`, `job_keys`, `applications`, `events`, `flags` |
