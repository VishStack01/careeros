# CareerOS Cloud: the multi-user service

CareerOS Cloud lets other job seekers sign up and use CareerOS without running anything
themselves. It is the same product as the personal setup: the same filters, the same
quoted checks, the same dashboard and the same apply rules. What changes is that one
service holds many accounts.

This page is the architecture, the deployment guide and the operations runbook. Read
[the release checklist](cloud-release-checklist.md) before inviting anyone.

## What it is

```mermaid
flowchart LR
  Scan["Hourly scan<br/>(GitHub Actions)"] --> Feed[("Public feed<br/>feed branch")]
  Feed --> Worker["Worker<br/>ingest · match · email · cleanup"]
  Worker --> DB[("PostgreSQL")]
  Browser["Dashboard + sign-in pages"] --> API["Web app / API<br/>(FastAPI)"]
  API --> DB
  API --> Files[("Resume files<br/>private volume")]
  Agent["Each user's Claude desktop app<br/>(their computer, their browser)"] -- "computer key" --> API
  Agent --> Forms["Company application forms"]
```

| Part | What it does | Code |
|---|---|---|
| Web app / API | Sign-up, sign-in, sessions, the dashboard, each user's documents and files, computer keys, the agent API | `careeros/cloud/app.py` |
| Worker | Reads the hourly feed into the shared inventory, matches every verified account against its own filters, sends email, cleans up | `careeros/cloud/worker.py`, `ingest.py`, `matching.py` |
| Database | PostgreSQL in staging and production, SQLite for development and tests. Versioned migrations | `careeros/cloud/db.py`, `careeros/cloud/migrations/` |
| Files | Resumes in a private directory, one folder per user | `careeros/cloud/storage.py` |
| Apply agent | Runs on each user's own computer in the Claude desktop app, using their own browser sign-ins. Talks to the API with a computer key | `careeros/cloud/prompts/apply.md` |

**The server never fills in employer forms and never holds anyone's job-site logins.**
Applications go out from each user's own computer, exactly as in the personal setup,
with the same stop rules. The server's job is to find and match roles, keep each
person's pipeline, and refuse a second submission for any role.

## Tenant boundaries

- **Shared:** the job inventory (`jobs`, `feed_state`). It holds public postings only.
- **Per account, keyed by `user_id`:** documents (filters, pipeline, application details,
  brain, runs), files, sessions, computer keys, application state, security events,
  match state. Every query for these filters by the signed-in user's id, so another
  account's record is simply "not found" (404), never "forbidden".
- **Deleting an account** removes every per-account row (foreign keys cascade) and the
  user's file folder at once. Backups roll over on your backup schedule; say how long
  in your privacy notice.

## Accounts and security

| Control | How |
|---|---|
| Passwords | PBKDF2-HMAC-SHA256, 600,000 iterations, random salt; rehashed on sign-in when the setting rises. At least 10 characters, common and email-based passwords refused. |
| Email verification | Required before the first sign-in. Links are single use, hashed in the database, expire in 24 hours and travel in the URL fragment so they never reach server logs. |
| Password reset | 1-hour single-use link; resetting signs out every session and emails a notice. |
| Enumeration | Sign-up, resend and reset give the same answer whether or not the email has an account; failed sign-ins spend the same time either way. |
| Sessions | Opaque tokens, only a SHA-256 stored; HttpOnly, SameSite=Lax, Secure on https cookies; 14-day expiry; "sign out everywhere". |
| CSRF | Cookie-authenticated writes need the `X-CareerOS-CSRF` header (a cross-site page can't send it without a CORS preflight, which the server never grants) and a matching Origin when one is sent. |
| Rate limits | Sign-in by IP and by email, sign-up, resend and reset in the database (shared across replicas); a per-process limit on all API calls. |
| Computer keys | `cos_k_…` tokens, hashed, shown once, up to 5 per account. They can read the pipeline and use `/api/agent/*` and uploads; they can't change documents directly, manage keys, export or delete the account. |
| Headers | CSP with a per-request script nonce, `frame-ancestors 'none'`, HSTS on https, nosniff, no referrer leaks, COOP. |
| Uploads | PDF only (magic bytes checked), size and per-account quota limits, served only to their owner, never executed. |
| Logs | One JSON line per request with method, path, status and timing; no tokens, bodies, query strings or resume text. |

Not included yet, and required before a broad public launch: two-factor sign-in or a
managed identity provider (OIDC), a malware scan of uploads, encryption of the upload
volume beyond your disk encryption, and an independent security review. See the
release checklist.

## Data flow, every hour

1. GitHub Actions scans about 1,400 company career pages and 9 remote boards and publishes
   the feed (see [feed.md](feed.md)).
2. The worker's scheduler queues an `ingest` task. Ingestion **fails closed**: an empty or
   unreadable feed, a missing summary, or an inventory that shrinks by more than half
   changes nothing. A role closes only when its company's board was read successfully and
   no longer lists it. Pay figures above 450 LPA are dropped as misreads.
3. After a successful ingest, the worker queues `match_user` for every verified account.
   Matching runs the same gates as the personal setup, with each person's filters, and
   writes new roles with their quoted checks, near-misses with what would change the
   decision, and closes or expires old ones. Roles a user queued or that need them are
   never expired. Saving filters queues a fresh match for that user.
4. Each user's Claude desktop app, on their schedule, asks `/api/agent/next` what to apply
   to, applies on the company's own form, and reports back.

The task queue is a table: tasks are claimed with a lease (`FOR UPDATE SKIP LOCKED` on
PostgreSQL), retried with exponential backoff up to their attempt limit, deduplicated
while queued or running, and reclaimed if a worker dies mid-task. Several workers can run.

## The apply agent API

All endpoints take `Authorization: Bearer <computer key>`.

| Endpoint | What |
|---|---|
| `GET /api/agent/next?limit=8` | Roles to try now, in order: roles the user queued, roles they approved, then (with auto-apply on) roles whose checks all passed. Fresh postings first, remote worldwide first, one per company, the daily cap applied, companies applied to in the last 180 days skipped. |
| `GET /api/agent/applicant` | Saved application details, the resume's text, and the Career Brain. |
| `GET /_blob/<id>` | A file (the resume) for the browser to attach. |
| `POST /api/agent/jobs/<id>/begin` | Call right before pressing Submit. 409 `already_submitted` or `needs_check` means don't. |
| `POST /api/agent/jobs/<id>/finish` | `{confirmed: true, confirmation, form, resumeAsset, ...}` marks it applied; `{confirmed: false}` leaves it for the user and blocks retries until they check. |
| `POST /api/agent/jobs/<id>/needs-you` | `{reason, applyUrl}`: the role shows under *Auto-apply needs you*. |
| `POST /api/agent/jobs/<id>/closed` / `fit` | The posting closed / the fit check result. |
| `POST /api/agent/heartbeat`, `/api/agent/runs` | "Your computer: linked", and the run log. |
| `POST /api/agent/brain` | Save the Career Brain built in the desktop app. |

The prompts users paste into the Claude desktop app are served, with your address filled
in, from the dashboard's *Brain & setup → Your computer* panel (`/api/prompts/apply`,
`/api/prompts/brain`).

## Deploy

### Option A: Render (managed)

1. Fork the repo and keep the `scan` workflow enabled (it publishes the feed), or leave
   `FEED_URL` pointing at the upstream feed.
2. In Render, **New → Blueprint** and pick your fork. `render.yaml` creates the database,
   the web service (with a 1 GB disk for resumes) and the worker, and runs migrations
   before each deploy.
3. Set `PUBLIC_URL` (your `https://` address), `SMTP_URL`, `MAIL_FROM` and
   `BOOTSTRAP_ADMIN_EMAIL`, then redeploy. Sign up with the admin email first.
   Optional: `LINKEDIN_CLIENT_ID` and `LINKEDIN_CLIENT_SECRET` add "Continue with
   LinkedIn" to the sign-in page (create an app at developer.linkedin.com, add the
   "Sign in with LinkedIn using OpenID Connect" product, and register
   `https://your.domain/api/auth/linkedin/callback` as the redirect URL).

A web service with a disk runs as one instance. To run more, move uploads to object
storage first (replace `LocalStorage` in `careeros/cloud/storage.py`).

### Option B: one server with Docker Compose

```bash
git clone https://github.com/VishStack01/careeros.git && cd careeros
cp .env.example .env     # set POSTGRES_PASSWORD, APP_ENV=production, PUBLIC_URL=https://your.domain,
                         # SMTP_URL, MAIL_FROM, BOOTSTRAP_ADMIN_EMAIL, TRUST_PROXY=1
DOMAIN=your.domain docker compose --profile https up -d --build
docker compose exec web careeros cloud check
```

Compose starts PostgreSQL (not exposed), applies migrations, then the web app (bound to
`127.0.0.1:8000`) and the worker; the `https` profile adds Caddy, which gets and renews
the certificate. Point your domain's DNS at the server first.

### Option C: your laptop, to try it

```bash
pip install -e ".[cloud]"
careeros cloud serve          # SQLite in data/cloud.db, emails printed to the terminal
careeros cloud worker         # in a second terminal
```

Open http://127.0.0.1:8000, sign up, and copy the confirmation link from the terminal.

## Configuration

Every setting is an environment variable; see `.env.example`. In `staging` and
`production` the app refuses to start without PostgreSQL, an `https://` `PUBLIC_URL`,
`SMTP_URL`, and applied migrations. `careeros cloud check` prints what's missing.

| Variable | Default | |
|---|---|---|
| `APP_ENV` | `development` | `development`, `staging` or `production` |
| `DATABASE_URL` | `sqlite:///data/cloud.db` | `postgresql://…` in staging and production |
| `PUBLIC_URL` | `http://127.0.0.1:8000` | Used in email links and the agent prompts; https turns on Secure cookies and HSTS |
| `SMTP_URL`, `MAIL_FROM` | console | `smtp://user:pass@host:587` (STARTTLS) or `smtps://…:465` |
| `SIGNUP_MODE`, `SIGNUP_ALLOWLIST` | `open` | `allowlist` with emails or `@domains` for a private beta; `closed` to stop sign-ups |
| `BOOTSTRAP_ADMIN_EMAIL` | | That account can read `/api/admin/overview` |
| `TRUST_PROXY` | `0` | `1` only behind your own reverse proxy, so client IPs come from `X-Forwarded-For` |
| `MAX_UPLOAD_MB`, `USER_STORAGE_MB` | 5, 25 | Per file and per account |
| `FEED_URL`, `INGEST_EVERY_MINUTES` | upstream feed, 60 | |
| `DB_POOL_MIN`, `DB_POOL_MAX` | 1, 10 | Per process. Keep `processes × DB_POOL_MAX` under the database's connection limit |

## Operate

**Release.** Back up the database, run `careeros cloud migrate` (Render does this in
`preDeployCommand`, Compose in the `migrate` service), deploy, then check `/api/ready`.
Never edit a migration that has run; add a new numbered file.

**Health.** `GET /api/health` is liveness. `GET /api/ready` checks the database and
migrations and reports the oldest queued task and the last ingest (503 when not ready).
`GET /api/admin/overview` (admin only) shows users, active roles, the feed, task counts by
status and recent failures.

**Alert on:** `/api/ready` failing; the last ingest older than 3 hours; queued tasks older
than 30 minutes; any `failed` tasks; database connections or disk near their limits;
backup failures; spikes in 401/429 responses.

**Backups.** Use your provider's automated PostgreSQL backups with point-in-time recovery,
back up the uploads volume on the same schedule, and do a restore drill before launch and
every quarter.

**Feed held back.** If ingestion refuses a feed that shrank sharply and you have checked the
scan is right, run `careeros cloud ingest --force`.

**Requests from users.** Export and deletion are self-service in *Brain & setup → Account*.
To disable an account, set `users.disabled_at`; its sessions and keys stop working at once.

**Scaling.** Run more workers freely. Run more web processes once uploads are in object
storage. Watch database connections first; add a read replica or a queue broker only when
measurements show the need.
