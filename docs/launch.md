# Launching CareerOS to users

Everything in the code is ready. Launching needs a handful of accounts that only you can open, and an afternoon of setup.

| What | Where | Why |
|---|---|---|
| Hosting | [Render](https://render.com) | Runs the web app, the worker and PostgreSQL from `render.yaml` |
| Email | Any SMTP provider (Resend, Brevo, Zoho Mail, Amazon SES) | Sign-up confirmation and password reset |
| Payments | [Razorpay](https://razorpay.com) | Pro subscriptions in rupees: UPI, cards, netbanking |
| AI | Anthropic, OpenAI or Google | The monthly AI allowance on the service's own model |
| Domain (recommended) | Any registrar | `app.yourdomain` looks trustworthy; Razorpay and the app stores prefer it |
| Google Play | Play Console (one-time registration fee) | The Android app |
| App Store | Apple Developer Program (yearly fee) | The iOS app |

## 1. Deploy the app on Render

1. In Render, choose **New > Blueprint** and pick this repository. It creates `careeros-web`, `careeros-worker` and `careeros-db`. The free tier isn't enough (workers and disks aren't free, and free databases expire), so check current prices at render.com/pricing before you confirm.
2. In `careeros-web`, set:
   - `PUBLIC_URL`: `https://careeros-web.onrender.com` or your domain
   - `SMTP_URL`: `smtps://user:password@smtp.yourprovider.com:465` and `MAIL_FROM`: `CareerOS <hello@yourdomain>`
   - `SUPPORT_EMAIL`: where users and Razorpay can reach you
   - `BOOTSTRAP_ADMIN_EMAIL`: your own email (this account becomes the operator)
   - `COMPANY_NAME`: your name or business name (shown on the policy pages)
   - `SECRETS_KEY` is generated for you; never change it after users save keys
3. Set the same `PUBLIC_URL`, `SMTP_URL`, `MAIL_FROM`, `SUPPORT_EMAIL` and `BOOTSTRAP_ADMIN_EMAIL` on `careeros-worker`.
4. Redeploy. The release step runs `careeros cloud migrate`. Open `https://<your-app>/api/ready`: it should say `"ok": true`.
5. Custom domain: add it in Render (Settings > Custom Domains), point the DNS record, then update `PUBLIC_URL` on both services.

## 2. Turn on the hosted AI allowance

Set `CAREEROS_LLM=anthropic` and `ANTHROPIC_API_KEY` on `careeros-web` (or `openai` / `gemini` with their key). Free accounts get `FREE_AI_CREDITS` actions a month (default 15) and Pro gets `PRO_AI_CREDITS` (default 400). Set a monthly spending limit in your provider's console. Users can always add their own key in Settings; those actions cost you nothing.

## 3. Take payments with Razorpay

1. Sign up and complete activation (KYC). Razorpay reviews your website: give it your app's address and these pages, which the app already serves:
   - Terms: `/terms`, Privacy: `/privacy`, Refunds and cancellation: `/refunds`, Contact: `/contact`, Pricing: `/pricing`
   Have the policy text reviewed for your situation first (it's a plain-language starting point, not legal advice).
2. Start in **Test mode**. Under Subscriptions > Plans, create a monthly plan at your Pro price (default ₹299). Copy its `plan_...` id.
3. Settings > API Keys: generate a key id and secret.
4. Settings > Webhooks: add `https://<your-app>/api/billing/webhook`, choose a secret, and select the `subscription.*` events (activated, charged, pending, halted, cancelled, completed, paused, resumed).
5. Set `RAZORPAY_KEY_ID`, `RAZORPAY_KEY_SECRET`, `RAZORPAY_WEBHOOK_SECRET` and `RAZORPAY_PLAN_PRO` on `careeros-web` and redeploy. The Upgrade button appears in Settings.
6. Test: upgrade with a Razorpay test card or UPI id, check the account shows Pro, cancel, and check the webhook log in Razorpay shows 200s.
7. Switch to **Live mode**: create the same plan and webhook again in live mode (ids differ) and replace the four values.

To give a beta tester Pro without payment, sign in as the operator and run in the browser console on the app:

```js
fetch("/api/admin/grant", {method: "POST", headers: {"Content-Type": "application/json", "X-CareerOS-CSRF": "1"},
  body: JSON.stringify({email: "friend@example.com", until: "2026-12-31"})}).then(r => r.json())
```

## 4. Fresh roles: the hourly scan

The app reads the public feed that `.github/workflows/scan.yml` publishes every hour. It is switched off right now. When you're ready to launch, turn it on with `gh workflow enable scan.yml` (or from the Actions tab) and check that a run finishes. The worker picks up the new feed within the hour.

## 5. The website

`website/index.html` has `<meta name="careeros-app" content="https://careeros-web.onrender.com">`. If your app lives elsewhere, change that one line; every "Start free" and policy link follows it. Pushing to `main` redeploys the website.

## 6. The phone apps

The web app is already installable (Add to Home Screen). For the stores, see [mobile/README.md](../mobile/README.md):

1. Run the **mobile** workflow with your app's address to get an Android `.apk` to try on your phone.
2. Google Play: create the app, upload the signed `.aab`, fill in Data safety and the privacy policy URL, add screenshots, and start with an internal or closed test track.
3. App Store: on a Mac, `npm run ios` in `mobile/`, archive in Xcode and submit through App Store Connect with a demo account for the reviewer.
4. Payments stay on the web: the apps hide the Upgrade button because the stores require their own billing for in-app subscriptions.

## 7. Before you invite people

- Work through [the release checklist](cloud-release-checklist.md): backups, monitoring, security review.
- Sign up with a fresh email from your phone and your laptop, confirm the email arrives, upload a resume, save filters and see roles appear after the next hourly ingest.
- Watch `/api/admin/overview` (as the operator) for sign-ups, plans, AI usage and failed tasks.
- Start with `SIGNUP_MODE=allowlist` and a small list in `SIGNUP_ALLOWLIST` if you want a private beta first.
