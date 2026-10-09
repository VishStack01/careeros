# CLAUDE.md

Read `AGENTS.md` first: it has the commands, the skill map and the hard rules.

Claude Code specifics:
- The skills in `.claude/skills/` load automatically. Start a new user with `career-brain`.
- For the reviewer step, prefer a second model (for example run the `reviewer` skill in Codex) so the drafter doesn't grade its own work.
- For browser steps outside Greenhouse, Lever and Ashby, use Claude in Chrome or the Claude desktop app's browser, following the `apply` skill's stop rules.
- Scheduled runs: `prompts/scheduled-search.md` and `prompts/scheduled-apply.md` are ready to paste into a scheduled task.
