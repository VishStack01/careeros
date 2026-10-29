---
name: outreach
description: Draft referral requests (from the user's LinkedIn connections), hiring-manager and recruiter notes, follow-ups on day 7 and 14 and post-interview thank-yous for a job. Drafts only; the user sends every message.
---

# Outreach (drafts only)

Referred candidates convert several times better than cold ones, and a short,
specific note to the hiring manager moves an application out of the pile.
Automating the sending would put the user's accounts and network at risk, so
this skill writes and the user sends.

## For each job at stage applied or ready
1. **Find the people** from public sources only: the posting, the company's team page, engineering blog authors, public talks. Record name, role and where you found them. Never guess email addresses; use one only if the company publishes it.
2. **Referral path**: people the user already knows come first. Read `profile/connections` on the dashboard (or run `careeros warm-intros --connections Connections.csv`): matches are tiered exact, strong (very likely) and weak (a similar name; never draft to one without saying so). Also check the brain for shared colleges, ex-colleagues and collaborators. If a warm path exists, draft the referral ask first (decision C): who you are, the role link, one proof point, and an easy out.
   **Referral finder**: when nobody is known there, WebSearch `site:linkedin.com/in "<company>" ("software engineer" OR SDE) "<college>"`, then the same without the college, then `"<company>" engineering manager`. From the result titles and snippets only (never open or scrape LinkedIn pages), write people.json `[{name, headline, url, location}]` and run `careeros referrals --company ... --title ... --people people.json --applicant applicant.json --json` (or `python3 careeros.pyz referrals ...`). Junior, associate and early-career engineers on the team the role belongs to come first (they reply most and know the hiring bar); also search `site:linkedin.com/in "<company>" ("junior" OR "associate" OR "SDE 1" OR "software engineer I")` and read the company's own team page. Save the top five to the job's `outreach.referrers` as `{name, headline, url, urlKind, source, why, level, score, note, ask, status: "draft"}`: `url` is the public profile from a search result, or a LinkedIn people-search link for `"<name>" <company>` (`urlKind: "search"`) when no profile URL is public; `note` is that person's connection note (under 300 characters) and `ask` the follow-up for after they accept. The Outreach page lists each one with Copy and Mark sent buttons. The dashboard also gives the user LinkedIn search links to open in their own signed-in browser.
3. **Hiring-manager note** (under 120 words): their team's problem from the brief, one proof point with a link, one ask (a 15-minute call or a look at the repo). Create it as a Gmail **draft** if Gmail is connected.
4. **Recruiter note**: shorter; confirms the hard requirements and availability.
5. **LinkedIn note** (under 300 characters): write it into the job's `outreach.linkedin.note`. The user pastes and sends it.
6. **Follow-ups**: the cadence is fixed (`careeros/followups.py`): day 7 and day 14 after applying, then stop; a reply to a recruiter within a day; a thank-you the day after each interview. Applied follow-ups close themselves once the company replies. Draft each one when it is due (`careeros followups`), adding something new (a relevant commit, a short teardown, a result), never "just checking in".
7. Run `careeros writing-check` on every draft and rewrite what it flags.

## Never
- Send LinkedIn messages or connection requests, or automate any LinkedIn action.
- Bulk-send, impersonate, or contact the same person twice in a week.
