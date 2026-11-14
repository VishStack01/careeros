# Propelo for Android and iOS

The phone apps are the hosted Propelo web app in a native shell built with [Capacitor](https://capacitorjs.com). The screens, the floating dock and the "Add..." sheet are the same code as the web dashboard, so every change to `dashboard/app.html` reaches the apps on the next page load, with no store release needed.

| | |
|---|---|
| App id | `io.github.vishstack01.careeros` (change it in `capacitor.config.json` before your first store upload; it can't change afterwards) |
| Server | `server.url` in `capacitor.config.json`, set with `CAREEROS_APP_URL` |
| Offline | `www/offline.html` ("You're offline", with Retry) |
| Icons and splash | generated from `assets/` with `npm run assets` |
| User agent | ends in `CareerOSApp/1.0`, so the web app knows it's inside the app |

## Build

```bash
cd mobile
npm ci
export CAREEROS_APP_URL=https://your-careeros-server   # your Render URL or custom domain
npm run android    # opens Android Studio: Run, or Build > Generate Signed Bundle
npm run ios        # opens Xcode (macOS): pick your team, then Product > Archive
```

No Android Studio? Run the **mobile** workflow from the GitHub Actions tab with your server's address. It builds a debug `.apk` you can install on your phone and a release `.aab` (signed when the keystore secrets are set; see the workflow file).

## Store checklist

- **Google Play:** a developer account (one-time fee), an upload keystore, the signed `.aab`, a privacy policy URL (`https://your-server/privacy`), the Data safety form (account details, resume files and job-search data; encrypted in transit; users can delete their account in the app), screenshots and a 512 px icon (`../careeros/cloud/static/app/icons/icon-512.png`).
- **App Store:** an Apple Developer Program membership (yearly fee), the bundle id registered, an archive uploaded from Xcode, a privacy policy URL, App Privacy answers, screenshots, and a demo account for the reviewer.
- **Payments inside the apps:** app stores require their own billing for digital subscriptions bought in an app, and don't allow pointing people to a website to buy. Inside the apps (the web app checks for `CareerOSApp` in the user agent), Settings shows only the plan the person is on and what it includes: no other plans, prices, currency switch, upgrade, cancel or invoice buttons. People manage plans on the website, and Pro or Ultra then works in the app too. Keep it that way unless you add store billing.
- **Sign-ins that leave the app:** the shell opens other websites in the phone's browser, so a sign-in that finishes there would never reach the app. Inside the apps, "Continue with LinkedIn" is hidden (email and password work), and connecting Gmail for automatic recruiter emails is done from the website; once connected, sending can be switched on and off in the app.
- **Review risk:** stores can reject apps that only wrap a website. Propelo ships its own app navigation, offline screen and installable icons, but expect reviewers to ask what the app adds; be ready to explain the job-tracking features and provide the demo account.
