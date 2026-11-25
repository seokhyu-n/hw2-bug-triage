# STATE (2026-11-25)

Branch: main (GitHub repo `seokhyu-n/hw2-bug-triage`, public since 11-25). Service setting = V3-Run-15 (headless; V3-Run-12 + code completeness, extract rules, tag guard). Tests: `venv\Scripts\python.exe -m pytest`.
## Where things are
- Reporter `/report`: optional fields, Galaxy/iPhone picker, screenshots + redaction, log, run record (`app/activity.py`), self-check guides (`app/self_help.py`), known issue/FAQ
  suggestions (`app/suggest.py`), public `/known-issues`, private status page `/status/<token>` with replies. Intake saves first, `app/intake.py`
  worker analyzes (retries; failures go to dev3).
- Developer `/` (dev1~3) -> `/app`: workflow state + message to reporter, same-symptom groups (`app/similar.py`),
  issue register/link/resolve-and-notify (`app/issues.py`, runtime `_issues.json`), reassign, 20 s refresh + P1 alert,
  chatbot (tools incl. guarded `assign_report`). Public endpoints rate-limited (`app/ratelimit.py`).
- Eval: v1 Run-01..07, v2 V2-Run-01..12, v3 (250) V3-Run-01..12, holdout (100) HO-Before/After x3 (`docs/analysis/v3_experiments.md`).
  Old prompts: `--prompts-dir`. Do not tune on `dataset_holdout.jsonl`. Feature evals `eval/feature_evals.py` (`--set v2`), `eval/chat_eval.py` (`--set hard`).
- Analysis page (4 tabs, the ONLY one; the 4 single-tab pages were deleted 11-24):
  https://claude.ai/artifact/XzpwoBQTWzGYMtCFiRppnX . Source `docs/artifacts/*.html`, rebuild with
  `build_combined.py`, publish the body only. Keep lecture page numbers/wording OUT of these pages.
## Setting up on another computer
- Clone, `python -m venv venv`, `venv\Scripts\python.exe -m pip install -r requirements.txt`.
- LLM calls: Claude Code headless (`claude -p`, `app/headless.py`), needs `claude` + `/login`, no key. `LLM_BACKEND=api` = old way with `.env`. Uses the account limits. Runtime data (`data/runtime/`) starts empty.
- Server: `venv\Scripts\python.exe -m uvicorn app.main:app --port 8000`.
- Also set up at `C:\Users\hi\부트캠프\hw2-bug-triage` (11-24); git author set repo-locally to match earlier commits.
## Done 11-25
- Setting = V3-Run-15 (headless, completeness 1/2 in code, data-tag guard, extract rules). Numbers and limits: `docs/analysis/v3_experiments.md` 8-9.
- Live analysis page = version 16 (published 11-25, V3-Run-15). Not done: screenshots/iPhone v3 sets not re-run headless (chatbot was: FE-CHAT-12/13); pre-warmed headless processes (speed) not built.
- Presentation: `docs/presentation/` (23-page PDF + 2 scripts). The private Slides artifact is the older 15-page one (no term lines, reporter features, whole screens, requirement page).
## Next (optional)
- Human label review done (34, `eval/review/v3_review_log.md`); after a label fix run `eval.regrade V3- HO-`. Harder holdout; iPhone / new-policy holdout cases.
- Known: E-342 (rhetorical question gets a question label); unquoted pasted reporter text can still name a receiver in chat.
- Eval runner must keep NOT importing `app.main` (registered issues stay out of eval).
- `.env` holds the real key; never read it. `data/faq.json` and the classify "정상 동작" list must change together.
