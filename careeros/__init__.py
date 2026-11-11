"""Propelo: an evidence-first job application agent.

The Python package holds the deterministic, testable parts of the system:
board scouts, requirement extraction, filter gates, dedupe, durable state,
the claims checker and the form-answer resolver. Judgement work (research,
tailoring, review) is done by the agent skills in `.claude/skills/`.
"""

__version__ = "1.3.0"
