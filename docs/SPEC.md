# SPEC (summary)

Full design: [docs/superpowers/specs/2026-11-21-runbuddy-bug-triage-design.md](superpowers/specs/2026-11-21-runbuddy-bug-triage-design.md)
Plan: [docs/superpowers/plans/2026-11-21-runbuddy-bug-triage.md](superpowers/plans/2026-11-21-runbuddy-bug-triage.md)

## What
A service that takes bug reports written by RunBuddy users and:
- classifies (bug / question / improvement request), extracts (environment, app version, repro steps),
  and scores (information completeness, priority);
- looks up existing issues and fixed versions (dummy JSON) via tools, linking only IDs that tool results contain;
- shows the developer a screen with linked issues and missing information.

## Constraints
- Login = developer ID only; no real DB, no deploy, no real issue tracker.
- Never fill in missing version/device/repro info: use `null` and show it as missing.
- Per-skill evaluation results and an improvement history (CSV/Excel); README has a technique-to-location table.
- API key never shown in screens, logs or commits.

## Stack
Python 3.12, FastAPI, Anthropic SDK, pytest. Models: claude-haiku-5-5 (default), claude-sonnet-5-5 (comparison run only).
