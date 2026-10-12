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
| autoApply | string | `queued` (you chose it for auto-apply) · `done` · `off` |
| needsYou, needsYouAt, applyUrl | string, ISO, URL | why auto-apply stopped on this role, and the form to finish it on |
| application | `{at, confirmation, form}` | what auto-apply saw after submitting |
| timeline | `[{at, event}]` | append-only history |
| notes | string | yours |

## `settings/profile`
Search and display settings: `experienceLevels`, `maxRequiredYears`,
`maxPostingAgeDays`, `locations`, `salaryFloorLpa`, `dailyCap`, `approvalMode`
(`auto-when-clear` · `daily-batch`), `schedule`.

## `profile/applicant`
What auto-apply puts into forms, entered on the dashboard's Brain & setup tab:
`fullName`, `email`, `phone`, `city`, `linkedin`, `github`, `portfolio`,
`currentTitle`, `currentCompany`, `experienceYears`, `noticePeriod`,
`currentCtcLpa`, `expectedCtcLpa`, `degree`, `college`, `graduationYear`,
`workAuthIndia`, `sponsorshipAbroad`, `relocate`, `gender`, `howHeard`, and
`resume {id, name, sizeBytes, uploadedAt}` (the PDF in the artifact's asset
store). Never stored: passwords, one-time codes, Aadhaar, PAN, bank details,
passport, date of birth. Only the artifact's owner can read it.

## `settings/applyRunner`
The auto-apply run's check-in: `{linked, lastSeenAt, device, browser, lastRunAt,
lastApplied, lastTriedAt, lastError}`. The dashboard shows "Your computer" as
linked when `lastSeenAt` is within 7 days.

## `brain/status`
`{state: "waiting" | "building" | "ready", summary, counts, missing[], updatedAt}`.
In the local setup the brain itself (`brain/brain.json`) stays on your machine;
in the hosted setup it is the `brain/brain` document, readable only by you. See
`brain/brain.example.json` for its schema.

## `runs/<id>`
`{startedAt, finishedAt, kind?, scanned, added, skipped, applied?, needsYou?, summary, error?}`.

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
