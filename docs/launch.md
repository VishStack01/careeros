# Launching Propelo

The code is ready. What's left needs accounts, money or a signature that only you can provide. Work through the list in order: each step says where to click and which setting it fills in.

## Your to-do list

| # | What | Time | Cost | Blocks |
|---|---|---|---|---|
| 1 | [Deploy on Render](#1-deploy-on-render) | 1 hour | Paid plan for web, worker and database | Everything |
| 2 | [Domain and email sending](#2-domain-and-email) | 1 hour + DNS wait | Domain, SMTP provider | Sign-ups, Razorpay review |
| 3 | [Hosted AI and a fallback](#3-hosted-ai) | 15 min | Model usage | AI allowance on paid plans |
| 4 | [Razorpay for India](#4-razorpay-rupees) | 1 to 5 days (KYC) | Fee per payment | Rupee checkout |
| 5 | [Dodo Payments for everyone else](#5-dodo-payments-dollars) | 1 to 3 days (review) | Fee per payment | Dollar checkout |
| 6 | [Google OAuth for recruiter emails](#6-gmail-sending) | 1 hour, then Google's review (weeks) | Free | Automatic recruiter emails for the public |
| 7 | [Business and tax](#7-business-and-tax) | Varies | Accountant | Live payments |
| 8 | [Backups, monitoring and a security test](#8-backups-monitoring-security) | Half a day | Small | Inviting people |
| 9 | [Store listings](#9-phone-apps) | 1 to 2 weeks with review | Play and Apple fees | The phone apps |
| 10 | [Repository settings and launch](#10-repository-and-launch) | 30 min | Free | Discovery |

## 1. Deploy on Render

1. In Render, choose **New > Blueprint** and pick this repository. It creates `careeros-web`, `careeros-worker` and `careeros-db`. The free tier isn't enough (workers and disks aren't free, and free databases expire); check prices at render.com/pricing before you confirm.
2. On `careeros-web`, set `PUBLIC_URL`, `SMTP_URL`, `MAIL_FROM`, `SUPPORT_EMAIL`, `BOOTSTRAP_ADMIN_EMAIL` (your own email: it becomes the operator) and `COMPANY_NAME`. `SECRETS_KEY` is generated for you. **Never change it** after users save keys or connect Gmail: everything encrypted with it becomes unreadable.
3. The worker copies most values from the web service. Set `PUBLIC_URL`, `SMTP_URL`, `MAIL_FROM`, `SUPPORT_EMAIL` and `BOOTSTRAP_ADMIN_EMAIL` on it too.
4. Redeploy. The release step runs `careeros cloud migrate`. `https://<your-app>/api/ready` should answer `"ok": true`.

## 2. Domain and email

1. Buy a domain and point `app.yourdomain` at Render (Settings > Custom Domains). Update `PUBLIC_URL` on both services.
2. Pick an SMTP provider (Resend, Brevo, Zoho Mail, Amazon SES). Add its **SPF**, **DKIM** and a **DMARC** record (start with `p=none`, move to `quarantine` after two clean weeks). Without them, confirmation emails land in spam.
3. Create `support@` and `security@` mailboxes and set `SUPPORT_EMAIL` and `SECURITY_EMAIL`. The second appears in `/.well-known/security.txt`.

## 3. Hosted AI

Set `CAREEROS_LLM=anthropic` and `ANTHROPIC_API_KEY` on `careeros-web` (or `openai` / `gemini` with their key). Add a second provider for outages: `CAREEROS_LLM_FALLBACK=openai` plus `OPENAI_API_KEY`. Set a monthly spending limit in each provider's console. Allowances: Free 15, Pro 400, Ultra 1,500 AI actions a month (`FREE_AI_CREDITS`, `PRO_AI_CREDITS`, `ULTRA_AI_CREDITS`). People's own keys cost you nothing.

Rough cost check before you set prices: an AI action is one model call of a few thousand tokens. Multiply your provider's price per call by 1,500 and make sure Ultra still leaves margin after payment fees and tax.

## 4. Razorpay (rupees)

1. Sign up and complete activation (KYC). Razorpay reviews your website: give it the app's address and these pages, which the app serves: `/terms`, `/privacy`, `/refunds`, `/contact`, `/pricing`. Have the policy text reviewed for your situation first; it's a plain-language starting point, not legal advice.
2. In **Test mode**, under Subscriptions > Plans, create two monthly plans: **Pro at ₹499** and **Ultra at ₹1,199**. Copy their `plan_...` ids.
3. Settings > API Keys: generate a key id and secret.
4. Settings > Webhooks: add `https://<your-app>/api/billing/webhook`, choose a secret, select the `subscription.*` events.
5. Set `RAZORPAY_KEY_ID`, `RAZORPAY_KEY_SECRET`, `RAZORPAY_WEBHOOK_SECRET`, `RAZORPAY_PLAN_PRO` and `RAZORPAY_PLAN_ULTRA` on `careeros-web` and redeploy.
6. Test with a test card or UPI id: upgrade to Pro, then switch to Ultra (Pro stays on until Ultra is paid, then Pro is cancelled for you), cancel, and check that Razorpay's webhook log shows 200s.
7. Go **Live**: create the same plans and webhook in live mode (the ids differ) and replace the values.

## 5. Dodo Payments (dollars)

Dodo is the merchant of record for sales outside India: it charges, files VAT and sales tax, and pays you out.

1. Sign up at dodopayments.com and complete business verification.
2. In test mode, create two subscription products: **Pro at $22.50 a month** and **Ultra at $48.50 a month**. Copy their `pdt_...` ids.
3. Developer > API keys: create a key. Developer > Webhooks: add `https://<your-app>/api/billing/dodo-webhook` and copy the `whsec_...` secret. Subscribe to the `subscription.*` events.
4. Set `DODO_API_KEY`, `DODO_WEBHOOK_SECRET`, `DODO_PRODUCT_PRO`, `DODO_PRODUCT_ULTRA` and `DODO_MODE=test`. Redeploy and run the same tests as for Razorpay, plus **Invoices and card** in Settings, which opens Dodo's customer portal.
5. Go live: create live products and webhook, replace the values and set `DODO_MODE=live`.

Two things in the Dodo integration follow its documentation as of this release but weren't tested against a live account: cancelling (`PATCH /subscriptions/{id}` with `cancel_at_next_billing_date`) and the customer portal link. Check both in test mode before going live.

## 6. Gmail sending

Automatic recruiter emails send from each person's own Gmail with the `gmail.send` permission only.

1. In Google Cloud console, create a project, enable the **Gmail API**, and set up the **OAuth consent screen** (External): app name Propelo, your support email, your domain, links to `/privacy` and `/terms`, scopes `openid`, `email` and `.../auth/gmail.send`.
2. Credentials > Create OAuth client (Web): redirect URI `https://<your-app>/api/mailbox/google/callback`. Set `GOOGLE_CLIENT_ID` and `GOOGLE_CLIENT_SECRET` on the web service (the worker copies them).
3. While the app is in **Testing**, only the test users you list (up to 100) can connect. That's enough for a beta.
4. To open it to everyone, submit the app for **verification**. `gmail.send` is a sensitive scope, so Google reviews the privacy policy (already includes the Limited Use statement), a demo video of the connect flow and the domain. Plan for a few weeks.
5. Keep sending reputation healthy: the limits are 10 a day on Pro and 25 on Ultra, only to addresses found on a public page, with an opt-out link and header on every email. Watch for complaints in `/api/admin/audit?kind=email-sent` and lower the limits if needed.

## 7. Business and tax

- **India:** charging for a service usually means GST registration once you cross the threshold, and Razorpay needs a business or individual KYC. Ask an accountant whether to start as a sole proprietor or register a company, and whether to show prices including GST (the pages say "includes GST where it applies").
- **Abroad:** Dodo handles sales tax and VAT as merchant of record, so you don't register in each country.
- Keep the refund promise on `/refunds` (7 days for mistakes and first payments) and answer `SUPPORT_EMAIL` within two working days.

## 8. Backups, monitoring, security

- **Backups:** turn on daily backups and point-in-time recovery for the database (Render PostgreSQL paid plans include them). Restore one into a scratch database once, following [the runbook](runbook.md).
- **Errors:** create a Sentry project and set `SENTRY_DSN` on both services (the Docker image includes the client). Only the error and route are sent.
- **Uptime:** point an uptime monitor at `/api/ready` every minute, alerting your phone.
- **Load:** run `k6 run scripts/loadtest.js` against a staging copy with 50 virtual users. The thresholds in the script are the bar: under 1% errors, reads under 400 ms at the 95th percentile.
- **Security:** the repository runs CodeQL, pip-audit, gitleaks and Dependabot. Before the public launch, get an independent penetration test of the web app, the billing webhooks and the Gmail flow, and turn on GitHub's private vulnerability reporting (Settings > Security).
- Work through [the release checklist](cloud-release-checklist.md).

## 9. Phone apps

The web app is installable already. For the stores, see [mobile/README.md](../mobile/README.md). Payments stay on the web: the apps hide upgrade buttons, because Apple and Google require their own billing for in-app digital subscriptions. Fill in Play's Data safety form and Apple's privacy labels from `/privacy`, and give reviewers a demo account.

## 10. Repository and launch

- In GitHub, set the repository's About: description, website `https://vishstack01.github.io/careeros/`, topics `job-search`, `ai-agent`, `india`, `open-source`, `career`, `resume`.
- Turn on the hourly scan: `gh workflow enable scan.yml`. The worker ingests every 15 minutes; Ultra accounts are matched on every ingest.
- `website/index.html` has `<meta name="careeros-app" content="https://careeros-web.onrender.com">`. Change it if the app lives on your domain.
- Start with `SIGNUP_MODE=allowlist` for a private beta, then open sign-ups.

To give someone a plan without payment, sign in as the operator and run in the browser console:

```js
fetch("/api/admin/grant", {method: "POST", headers: {"Content-Type": "application/json", "X-CareerOS-CSRF": "1"},
  body: JSON.stringify({email: "friend@example.com", plan: "ultra", until: "2026-12-31"})}).then(r => r.json())
```
