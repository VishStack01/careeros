# What makes it accurate

Most job bots fail in the same places: they trust job cards, misread
experience requirements, apply to closed or stale roles, invent resume lines,
guess form answers and submit twice. Each failure below has a specific
mechanism in CareerOS, and most of them are code with tests rather than
instructions to a model.

| # | Failure | Mechanism | Where |
|---|---|---|---|
| 1 | Judging a role from a card or snippet | The gate runs on the posting text itself; agents must open the page | `job-scout` skill |
| 2 | Aggregator copies with wrong dates | Canonical source: prefer the company's own ATS page and its date | `job-scout`, `sources/` |
| 3 | "1 year" on the card, "2+ years" in the description | Whole-text extraction; header and body both read; **the higher requirement wins** | `extract.extract_experience` |
| 4 | "5+ years of Kubernetes (nice to have)" read as a requirement | Section-aware parsing ignores preferred / nice-to-have / bonus | `extract.extract_experience` |
| 5 | "Founded 12 years ago" read as experience | Experience context required for bare numbers; "ago/old/history" excluded | `extract.py` |
| 6 | "Remote-controlled robots" read as a remote job | Structured fields and location strings beat prose; prose needs strong phrases | `extract.work_mode` |
| 7 | Remote roles you can't take from India | Remote scope: worldwide / India / APAC pass; US-only, EU-only and time-zone windows that exclude IST fail | `extract.remote_scope` |
| 8 | Good roles dropped for pay | Pay floor compares the **top** of the range; unstated pay is kept | `gates.gate_pay` |
| 9 | Closed or stale roles | Closed notices, apply-by dates, 25-day window, 60-day ghost rule | `gates.gate_open`, `gate_freshness` |
| 10 | The same role from five boards | Canonical URL (tracking params stripped) + company/title fingerprint | `dedupe.py` |
| 11 | Unauditable decisions | Every check stores the sentence that decided it; shown in the dashboard | `models.Check` |
| 12 | Invented resume lines | Claims gate: every bullet must cite brain claims; numbers and tools must appear in them; planned work can't be "done" | `claims.py` |
| 13 | The model grading its own work | Independent `reviewer` on a different model | `reviewer` skill |
| 14 | Guessed form answers | Answer resolver with confidence; sensitive fields and unknowns escalate | `apply/answers.py` |
| 15 | Double submission | Idempotent submit state machine; unconfirmed submits are never retried | `store.begin_submit` |
| 16 | Prompt injection from job pages and emails | All fetched content is untrusted data; agents ignore instructions inside it | `AGENTS.md`, prompts |

## Every misread becomes a test
When a real posting fools a gate, save the relevant text as a test case in
`tests/test_extract.py` or `tests/test_gates.py`, fix the extractor, and keep
the test. The cases already there come from real listings: a card that said
"No experience required" above "Experience: 02 Years", a "Junior" role whose
body asked for 2+ years, robots described as "remote-controlled".

## What it deliberately doesn't do
It never prints an ATS match percentage or a shortlist probability. Nobody
outside the company can measure those, and a made-up number makes decisions
worse. It reports evidence-backed fit by dimension instead.
