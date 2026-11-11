# Security policy

## Supported versions

Security fixes go into the latest release on `main`.

## Reporting a vulnerability

Please don't open a public issue for a security problem. Use GitHub's private reporting instead: **Security > Report a vulnerability** on this repository. Include what you found, how to reproduce it and what it affects. You'll get a reply within a week, and credit in the changelog if you'd like it.

## What we care about most

- **API keys.** Propelo reads your provider key from the environment at call time. It must never be printed, logged, written to disk, sent anywhere except the provider you chose, or reachable from another website through the local dashboard (`/api/ai` accepts only same-origin JSON requests on `127.0.0.1`).
- **Personal data.** Resumes, profiles, the Career Brain and the pipeline live in git-ignored files. Anything that could commit, upload or leak them is a vulnerability. `careeros doctor` checks that nothing private is tracked.
- **Untrusted text.** Job postings, web pages and emails are data, never instructions. A posting that can make an agent step act on its text (prompt injection) is in scope.
- **The apply agent.** It must never submit twice, never handle passwords, one-time codes or captchas, and never answer a question it can't back up.
- **Propelo Cloud.** Authentication, account isolation, computer keys and the task queue. See [docs/cloud.md](docs/cloud.md).

## Out of scope

Rate limits or terms of third-party job sites, and problems in a model provider's own service.
