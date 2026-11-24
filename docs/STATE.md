# STATE (2026-11-24)

Branch: main (GitHub private repo `seokhyu-n/hw2-bug-triage`). Service setting = V2-Run-12 (V2-Run-11 iPhone support, 3x repeated, + fixed-version link rule). Tests: `venv\Scripts\python.exe -m pytest`.

## Where things are
- Reporter `/report`: optional fields (`app/report_form.py`), screenshots + redaction, log, pre-submit known issue/FAQ
  suggestions (`app/suggest.py`), private status page `/status/<token>` with replies. Intake saves first, `app/intake.py`
  worker analyzes (retries; failures go to dev3).
- Developer `/` (dev1~3) -> `/app`: workflow state + message to reporter, same-symptom groups (`app/similar.py`),
  issue register/link/resolve-and-notify (`app/issues.py`, runtime `_issues.json`), reassign, 20 s refresh + P1 alert,
  chatbot (tools incl. guarded `assign_report`). Public endpoints rate-limited (`app/ratelimit.py`).
- Eval: v1 Run-01..07, repeats, dataset_v2 V2-Run-01/07/08/09/10 (`docs/analysis/run_08_10.md`),
  feature evals `eval/feature_evals.py` -> `eval/feature_evals.csv` + Excel "추가 기능 평가".
- Analysis page (4 tabs, the ONLY one; the 4 single-tab pages were deleted 11-24):
  https://claude.ai/artifact/XzpwoBQTWzGYMtCFiRppnX . Source `docs/artifacts/*.html`, rebuild with
  `build_combined.py`, publish the body only. Keep lecture page numbers/wording OUT of these pages.

## Setting up on another computer
- Clone, `python -m venv venv`, `venv\Scripts\python.exe -m pip install -r requirements.txt`.
- The user creates `.env` with `CLAUDE_API_KEY=...` (not in git). Runtime data (`data/runtime/`) starts empty.
- Server: `venv\Scripts\python.exe -m uvicorn app.main:app --port 8000`.
- Also set up at `C:\Users\hi\부트캠프\hw2-bug-triage` (11-24); git author set repo-locally to match earlier commits.

## Next (optional)
- Remaining class errors E-053/E-113/E-116; E-090 ("최신" version) link; MAE (Run-11 x3 0.108-0.154, Run-12 0.092).
- Eval runner must keep NOT importing `app.main` (registered issues stay out of eval).
- `.env` holds the real key; never read it. `data/faq.json` and the classify "정상 동작" list must change together.
