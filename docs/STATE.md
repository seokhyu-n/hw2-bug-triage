# STATE (2026-11-24)

Branch: main (GitHub private repo `seokhyu-n/hw2-bug-triage`). 191 tests pass. Reports carry up to 3 screenshots (`app/attachments.py`), read by the extract step.

## Where things are
- Reporter page `/report` (no login) -> `POST /api/intake` saves to `data/runtime/_intake/`, returns receipt at once ->
  `app/intake.py` worker: 4-step analysis (retry 5s/30s) -> auto-assigned by feature_area; failures stay as
  "분석 실패" for dev3 with retry button (dev1 tracking/voice/login, dev2 map/record/card_image, dev3 ai_chat/other + fallback)
- Developer page `/` login (dev1~3) -> `/app`: own reports, detail, reanalyze, chatbot (streamed via `POST /api/chat/stream`)
- Eval: `eval/dataset_v1.jsonl` (100, frozen), Run-01..07 in `eval/runs.csv`, `eval/runs.xlsx` (per-task sheets).
  Final setting = Run-07 (Haiku 5.5, few-shot + rubric + context select + 2 prompt fixes)
- Analysis page (one page, 4 tabs): https://claude.ai/artifact/XzpwoBQTWzGYMtCFiRppnX
  source `docs/artifacts/assignment2.html`, rebuilt from the 4 tab pages by `docs/artifacts/build_combined.py`.
  Keep lecture page numbers / lecture wording OUT of the analysis pages (user request).

## Eval strengthening (done, see docs/analysis/eval_strengthening.md)
- Repeats: Run-04/Run-07 x3 (priority/extraction gains beyond noise; completeness MAE noisy). 56 labels human-checked, 0 fixes (`eval/review/review_log.md`)
- dataset_v2 (120 = v1 + E-101..E-120, `--dataset v2`): final setting is worse than baseline on the new boundary cases
  (question->bug, P3->P2 over-rating). Next: rubric core/auxiliary feature scope; classify few-shot + feature list

## Setting up on another computer (e.g. academy PC; also done at `C:\Users\hi\부트캠프\hw2-bug-triage` on 11-24)
- `gh repo clone seokhyu-n/hw2-bug-triage` into `C:\dev\fde`, then `python -m venv venv`
- `venv\Scripts\python.exe -m pip install -r requirements.txt`
- The user creates `.env` with `CLAUDE_API_KEY=...` themselves (not in git). Runtime data (`data/runtime/`) starts empty.
- Server: `venv\Scripts\python.exe -m uvicorn app.main:app --port 8000` -> http://127.0.0.1:8000

## Next (optional)
- Improvement candidates: see Eval strengthening above; link rule "app_version >= fixed_in -> no link"
- Sync between home and academy: `git pull` before work, commit + `git push` after
- `.env` holds the real key; never read it. Dataset labels: versions digits only, non-bugs P4 + completeness null.
