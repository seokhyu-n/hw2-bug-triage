# RunBuddy Bug Triage Service

FastAPI + Anthropic SDK service that classifies, extracts and scores bug reports for the
RunBuddy app (bootcamp week-1 assignment 2). Design: `docs/superpowers/specs/2026-11-21-runbuddy-bug-triage-design.md`.

@docs/SPEC.md
@docs/STATE.md

## Environment (Windows 11)
- Work folder: `C:\dev\fde\hw2-bug-triage`. Python 3.12, virtualenv named `venv`.
- Always call pip through the venv interpreter: `venv\Scripts\python.exe -m pip install -r requirements.txt`. Never use `pip.exe`.
- Run tests: `venv\Scripts\python.exe -m pytest -v`
- Run the server: `venv\Scripts\python.exe -m uvicorn app.main:app --port 8000` (reporter page `/report`, developer login `/`)
- Remote: GitHub private repo `seokhyu-n/hw2-bug-triage` (main). Pull before work, push after.
- Use Windows (PowerShell) commands and backslash paths in instructions for the user.

## API key and `.env`
- The key lives in `.env` as `CLAUDE_API_KEY`. `.env` is git-ignored.
- NEVER overwrite, recreate or edit an existing `.env`. The user pastes the real key.
- NEVER read, print, log, echo, copy or commit the key value (not in code, tests, docs, commits or chat).
- Load it only through `app.config.get_api_key()`.

## Model policy
- API calls during development use claude-haiku-5-5 only; the single exception is the Sonnet 5.5 model-comparison eval run.
- Tests use a fake client; real calls only in explicitly marked manual verification steps.

## Conventions
- Prices and model names live in `app/config.py` only.
- `tool_choice` is always `auto`. Never invent facts missing from a report: use `null` and list it as missing information.

## State management (lecture p.78)
- Import `@docs/SPEC.md` (what we build) and `@docs/STATE.md` (where we are) at session start.
- After every step, OVERWRITE `docs/STATE.md`, keeping it within 30 lines.
- When a task finishes, add an entry at the TOP of `docs/HISTORY.md`.
- Do NOT import `docs/HISTORY.md` with `@`; read it only when needed.
- Maintain these files on your own, even if the user does not ask.
