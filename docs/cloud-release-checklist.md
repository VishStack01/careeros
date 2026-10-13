# CareerOS Cloud release checklist

A passing test run is not a launch approval. Tick these in order; the first section is
what the code already does, so you can see where the remaining work is.

## Built and tested in this repository

- [x] Per-account isolation on every document, file, key, session and application record (cross-account reads return 404; tested).
- [x] Email verification before first sign-in; single-use, hashed, expiring links; password reset that signs out everywhere.
- [x] PBKDF2-SHA256 password hashing, password rules, enumeration-resistant answers, constant-time failure path.
- [x] HttpOnly, SameSite session cookies; CSRF header and Origin check on writes; CSP with script nonces; security headers.
- [x] Database-backed rate limits on sign-in, sign-up, resend and reset.
- [x] Computer keys scoped to the agent API; revocable; shown once.
- [x] Export and self-service account deletion (cascading, files removed).
- [x] Durable task queue with leases, retries, backoff and dedupe; concurrent workers never double-claim (tested on PostgreSQL).
- [x] Feed ingestion fails closed (empty, unreadable, missing summary, sharp shrink); closures only for boards read successfully.
- [x] One submission per role, ever: `begin` / `finish` state machine; unconfirmed submits block retries until the user checks.
- [x] Production refuses SQLite, plain-http `PUBLIC_URL`, missing SMTP and pending migrations.
- [x] The full test suite runs on SQLite and on a real PostgreSQL 16 (CI runs both).

## Before inviting anyone (private beta)

- [ ] Deploy to staging with `APP_ENV=staging`; `careeros cloud check` reports nothing.
- [ ] HTTPS end to end; the database has no public address; `TRUST_PROXY=1` only behind your proxy.
- [ ] SMTP from a domain with SPF, DKIM and DMARC; confirmation and reset emails arrive and aren't marked spam.
- [ ] `SIGNUP_MODE=allowlist` for the beta; `BOOTSTRAP_ADMIN_EMAIL` set before the first sign-up.
- [ ] Automated database backups with point-in-time recovery, uploads backed up, and one restore drill done and timed.
- [ ] Uptime check on `/api/ready`; alerts for a stale ingest, old queued tasks, failed tasks, database capacity.
- [ ] Privacy notice and terms (`/privacy`, `/terms`) reviewed for your jurisdiction (India: DPDP Act 2023) with your contact details; a support address that someone reads.
- [ ] A short incident plan: who is paged, how to disable sign-ups (`SIGNUP_MODE=closed`), how to revoke all sessions and keys.
- [ ] Run the apply agent end to end for two test accounts on real Greenhouse, Lever and Ashby postings you're happy to apply to; check every field and the confirmation.

## Before opening sign-ups to the public

- [ ] Two-factor sign-in, or sign-in through a managed identity provider (Google, Microsoft) with OIDC.
- [ ] Uploads in private object storage with encryption, short-lived signed downloads and a malware scan; deletion covers backups as your notice promises.
- [ ] Independent security review and penetration test (tenant isolation, CSRF, session theft, upload handling, prompt injection through postings and resumes).
- [ ] Load test: sign-in, `/api/c/jobs` for large pipelines, the worker matching 1,000+ accounts within the hour; database connection budget checked.
- [ ] Abuse controls: per-account quotas reviewed, a way to report abuse, a policy for disabling accounts.
- [ ] Dependency, container and secret scanning in CI.

## Before any claim about results

- [ ] A hand-checked set of postings with known right answers for each gate; precision and recall measured in CI.
- [ ] Freshness, duplicate and broken-link rates measured on the live inventory.
- [ ] Outcomes (screens per application) measured per cohort before any marketing claim. Never show a "chance of getting shortlisted".
