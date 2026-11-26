# STATE (2026-11-27)

Branch: main (GitHub repo `seokhyu-n/hw2-bug-triage`, public since 11-25). Service setting = V3-Run-18 (headless; code completeness + P1->P2 rule, extract rules, tag guard, 11-26 priority rubric incl. battery/missing-record + 3 product policies). v3 cls 0.979 / priority 0.937, holdout 0.967, holdout2 0.967. Tests: `venv\Scripts\python.exe -m pytest`.
## Where things are
- Reporter `/report`: optional fields, Galaxy/iPhone picker, screenshots + redaction, log, run record (`app/activity.py`), self-check guides (`app/self_help.py`), known issue/FAQ
  suggestions (`app/suggest.py`), public `/known-issues`, private status page `/status/<token>` with replies. Intake saves first, `app/intake.py`
  worker analyzes (retries; failures go to dev3).
- Developer `/` (dev1~3) -> `/app`: workflow state + message to reporter, same-symptom groups (`app/similar.py`),
  issue register/link/resolve-and-notify (`app/issues.py`, runtime `_issues.json`), reassign, 20 s refresh + P1 alert,
  chatbot (tools incl. guarded `assign_report`). Public endpoints rate-limited (`app/ratelimit.py`).
- Eval: v1 Run-01..07, v2 V2-Run-01..12, v3 (250) V3-Run-01..18, holdout (100) HO- x3, holdout2 (100, harder, blind) HO2-Run-16/17/18 x3 (`docs/analysis/v3_experiments.md` 11-13).
  Old prompts: `--prompts-dir`. Do not tune on `dataset_holdout.jsonl` / `dataset_holdout2.jsonl`. Feature evals `eval/feature_evals.py` (`--set v2`), `eval/chat_eval.py` (`--set hard`).
- Analysis page (4 tabs, the ONLY one; the 4 single-tab pages were deleted 11-24):
  https://claude.ai/artifact/XzpwoBQTWzGYMtCFiRppnX . Source `docs/artifacts/*.html`, rebuild with
  `build_combined.py`, publish the body only. Keep lecture page numbers/wording OUT of these pages.
## Setting up on another computer
- Clone, `python -m venv venv`, `venv\Scripts\python.exe -m pip install -r requirements.txt`.
- LLM calls: Claude Code headless (`claude -p`, `app/headless.py`), needs `claude` + `/login`, no key. `LLM_BACKEND=api` = old way with `.env`. Uses the account limits. Runtime data (`data/runtime/`) starts empty.
- Server: `venv\Scripts\python.exe -m uvicorn app.main:app --port 8000`.
- Also set up at `C:\Users\hi\부트캠프\hw2-bug-triage` (11-24) and `C:\dev\fde\hw2-bug-triage` (11-26, git author not set there yet).
## Done 11-25 / 11-26
- Live analysis page = version 17 (published 11-27, V3-Run-18: summary KPIs, chain rules, evaluation 12). Pre-warmed headless processes (speed) not built (decided).
- Presentation (11-26): 16 pages = 14 in the course template order (reason+app, architecture, core logic, results, limits) + 2 whole screens at the end. Source = private Slides artifact
  https://claude.ai/artifact/Pu2oAvFYpLiDiYygAeyL63 ; copy in `docs/presentation/deck/`, PDF via `deck/build_pdf.py` (Edge). Edit the artifact, copy files back, rebuild.
- 11-26 product policies (no auto pause, staged rollout, AI coach English terms = normal; account lock / grace = bug, E-144/E-148): V3-Run-17 non-bug called bug 4-5 -> 1-2. Presentation p.11/14 updated.
## Next (optional)
- Human label review done (34, `eval/review/v3_review_log.md`); after a label fix run `eval.regrade V3- HO-`. Harder holdout; iPhone / new-policy holdout cases.
- Known: E-342 (rhetorical question gets a question label); unquoted pasted reporter text can still name a receiver in chat. Priority: 9 v3 cases wrong 3/3 (battery = P2, today's run missing = P2 / older record = P1 decided 11-26). Classification noise: E-386 holdout 3/3 bug, E-020/148/177 sometimes not bug. `limited_scope` must be set by hand for registered issues.
- Eval runner must keep NOT importing `app.main` (registered issues stay out of eval).
- `.env` holds the real key; never read it. `data/faq.json` and the classify "정상 동작" list must change together.
