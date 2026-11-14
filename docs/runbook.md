# Runbook

What to do when something goes wrong in Propelo Cloud. Keep this open during the first weeks after launch.

## Where to look first

| Signal | Where |
|---|---|
| Is the app up? | `/api/ready` (database and migrations), `/api/health` |
| What happened to one request | Every response has `X-Request-ID`; search the logs for that id (`"rid"`) |
| Errors | Sentry, when `SENTRY_DSN` is set; otherwise Render's logs |
| Background work | `/api/admin/overview` as the operator: tasks by status and the last ten failures |
| Security and billing events | `/api/admin/audit`, filter with `?kind=` (for example `plan-activated`, `checkout-started`, `email-sent`, `gmail-connected`, `export`) |

## Incidents

**Severity.** S1: the app is down, data is exposed or people are charged wrongly. S2: a feature is broken for many people (payments, sign-up, matching, sending). S3: anything else.

For S1 and S2:

1. Note the time and open a private incident note.
2. Stop the damage first:
   - Automatic emails misbehaving: remove `GOOGLE_CLIENT_ID` from both services and redeploy. Nothing more is sent; queued emails wait.
   - Auto-apply misbehaving: it runs on people's own computers, so post a notice and ask users to press **Pause** in Auto-apply. The server keeps refusing duplicate and unsafe submissions.
   - Wrong charges: switch the affected provider off by removing its keys (`RAZORPAY_KEY_ID` or `DODO_API_KEY`); existing plans keep working because entitlement is read from the database.
   - Suspected key leak: rotate the leaked secret at its provider and in Render. Don't rotate `SECRETS_KEY` unless it leaked (see below).
3. Fix, deploy, and confirm with the request ids and audit events.
4. Tell affected people by email within 72 hours if their data was involved, and say what happened in plain words.
5. Write down what happened, why, and the one change that stops it happening again.

## Payments

- **A webhook failed.** Both providers retry for hours (Dodo up to 8 times). Events are stored once by id, so replaying is safe: in the provider's dashboard, resend the event. Events older than the latest one applied are ignored on purpose.
- **Someone paid but is still on Free.** Check `/api/admin/audit?kind=checkout-started` for their account, then the provider's webhook log. If the event never arrived, resend it. As a stopgap, grant the plan with `/api/admin/grant` and a short `until`.
- **Someone is charged for two plans.** After a plan change the worker cancels the old subscription (task `billing_cancel`). If that task failed, cancel the old subscription in the provider's dashboard and refund the overlap.
- **Refunds** are issued in the provider's dashboard. Cancelling there is mirrored back to Propelo by webhook.

## Gmail sending

- A mailbox shows "Gmail stopped accepting sends": the person revoked access or changed their password. They reconnect from Outreach; nothing is lost.
- A send marked "Check your Gmail" may have gone out (a network failure after Gmail received it). It's never retried automatically. The person checks their Sent folder.
- Complaints: if a recipient writes to support, add their address to the opt-out list by opening their opt-out link, or with SQL: `INSERT INTO email_optouts(address_hash, at) VALUES (sha256(lower(address)), now())`.

## Backups and recovery

- Daily backups and point-in-time recovery come from the database host. Check they are on.
- **Restore drill (every quarter):** restore the latest backup into a new database, point a staging copy of the app at it with the same `SECRETS_KEY`, sign in as a test user and open their pipeline. Write down how long it took.
- Uploaded files live on the web service's disk (`UPLOAD_DIR`). Back that disk up too, or move uploads to object storage before you have many users.
- **`SECRETS_KEY`** decrypts users' own AI keys and Gmail permissions. Store a copy in a password manager. If it leaks: set a new one, then ask everyone to save their AI key again and reconnect Gmail (the old values can't be read any more).

## Deploys and rollbacks

- Every push to `main` runs tests, CodeQL and the security checks. Deploy only green commits.
- Migrations only add columns and tables, so rolling back the app to the previous release is safe; never roll back a migration by hand.
- To roll back: in Render, redeploy the previous successful deploy.

## Capacity

- `k6 run scripts/loadtest.js` against staging gives the baseline. Re-run it before a launch post or a big email.
- If the worker falls behind (queued tasks growing in `/api/admin/overview`), add a second worker instance; tasks are claimed with leases, so several workers are safe.
