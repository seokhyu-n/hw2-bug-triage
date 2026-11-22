# HISTORY

Newest entry on top.
## 2026-11-22 Analysis pages merged, repo on GitHub
- Four analysis pages combined into one tabbed page (`docs/artifacts/assignment2.html`, builder `build_combined.py`); lecture references removed at the user's request.
- Project pushed to private GitHub repo `seokhyu-n/hw2-bug-triage` so it can run on the academy PC; STATE rewritten with setup steps for another computer.
## 2026-11-22 Streaming chatbot and per-task eval sheets (PDF gap check)
- Gap check against lecture p65/p68: all required items present; `stream` (p14 key parameter) was unused and eval results were not split by task.
- `app/llm.py`: `call_llm(on_text=...)` streams via `client.messages.stream()` (`text_stream`, `get_final_message()`), same LLMResult. `app/chat.py`: `chat_turn(on_text, on_tool)`. New `POST /api/chat/stream` (NDJSON text/tool/done/error); UI renders replies as they arrive. Verified live: one reply = 13 text chunks.
- `eval/run_eval.py:build_xlsx`: sheets 전체 Run + 분류/추출/스코어링/이슈 연결/속도·비용 (metrics, delta vs previous run of the same model, 변경사항, bar chart) + 혼동행렬 per run; `-smoke` runs excluded from Excel only. runs.xlsx regenerated (no API calls).
- README: streaming, task sheets, how the eval set was made. 154 tests pass.
## 2026-11-22 Split reporter intake from developer screen
- New public page `/report` + `POST /api/intake` (no login): reporter gets only the receipt number; triage result and assignee stay on the developer side. Assignment by `feature_area` unchanged.
- Removed the authenticated `POST /api/reports` and the report input box from `/app`; added a refresh button. Login page links to `/report`.
- Why: in practice reporters (users/QA/support) and developers use separate channels; developers should not type reports. Report IDs (R-0001) kept as is (user's choice).
- tests/test_api.py rewritten for the intake flow (147 tests pass). README updated; known limit: intake has no rate limit.
## 2026-11-22 Final whole-branch review fixes
- `app/llm.py`: missing key -> `LLMError` (Korean message), trailing `anthropic.APIError` clause (502 instead of bare 500).
- `app/chat.py`: fallback ChatReply when `call_llm` fails after a successful reanalyze; reanalyze guard also needs added_info >= 4 chars and a request_id from the current message or recent IDs (`_recent_ids`, shared with `summarize_state`).
- `app/pipeline.py` `analyze` attaches `partial_logs` to raised exceptions; `eval/run_eval.py` counts their cost/cache for failed cases (latency still excluded from the mean).
- `static/app.js`: chat reanalyze refreshes the selected report detail. README filter wording and evaluation.html 누락률 (0.005) corrected. 146 tests pass.

## 2026-11-22 Task 11: README and analysis artifacts
- `README.md` (Korean): service intro, architecture, Windows run steps, p.68 technique -> file:function table, Run-01..07 table + Haiku-vs-Sonnet reasoning, prefix cache numbers, security, known limits; artifact links left as placeholders.
- `docs/artifacts/` chaining / function_calling / service_workflow / evaluation HTML (self-contained, light/dark, phone-safe; metrics generated from `eval/runs.csv`, 25 hard cases from `eval/hard_cases.md`).
- `requirements.lock.txt` from pip freeze. 137 tests pass; server booted and stopped.

## 2026-11-22 Task 10: baseline and one-variable experiments
- Runs (Haiku unless noted, 100 cases, 0 errors): Run-01 baseline / Run-02 +few-shot / Run-03 +rubric / Run-04 +context select (default) / Run-05 Sonnet / Run-06 extract feature_area for non-bugs / Run-07 rubric P1 rule. Total spend ~$2.11 (Sonnet $1.57).
- Ablation: rubric had the biggest effect on scoring (completeness MAE 0.34 -> 0.18), context select cut MAE to 0.11 at lower cost; few-shot helped priority but caused 2 bug over-classifications (E-021, E-052).
- Improvement 1 (Run-06, kept): all 13 Run-04 feature_area misses were non-bug reports (prompt tied it to the symptom); extraction 0.950 -> 0.972, miss rate 0.068 -> 0.005, hallucination 0.018 -> 0.025 (2 null cases filled as `other`); completeness MAE 0.107 -> 0.143 and priority ±1 0.98 -> 0.97 got worse (MAE back to 0.109 in Run-07).
- Improvement 2 (Run-07, kept): rubric no longer lets "unknown scope" demote a confirmed crash/login failure/record loss; priority exact 0.84 -> 0.88, P1 recall 10/16 -> 15/16, one new over-rating (E-065). No change reverted.
- Final setting: Haiku 5.5 + few_shot + rubric + context_select + both fixes (Run-07). Quality first: classification accuracy equal (0.98) and extraction higher than Sonnet (0.972 vs 0.962); Sonnet (Run-05) is ahead on labels (0.98 vs 0.95), link (0.97 vs 0.96), priority exact (0.93 vs 0.88) and completeness MAE (0.036 vs 0.109), at ~18x cost ($1.568 vs $0.087 / 100) and +36% latency vs Run-07 (10.93s vs 8.06s). The gaps were judged not worth the cost and latency, so Haiku. Sonnet with the improved prompts was not run.
- Analysis: `docs/analysis/run_comparison.md`, `docs/analysis/error_analysis.md`.

## 2026-11-21 Task 9: grading and eval runner
- `eval/grade.py` (pure metrics), `eval/run_eval.py` (CLI: per-case CSV, confusion CSV, predictions JSONL, cumulative `eval/runs.csv` + `runs.xlsx`; --workers, errors recorded as 오류). `Run-00-smoke` (3 cases, Haiku) kept. 135 tests pass.

## 2026-11-21 Task 8: evaluation dataset v1
- `eval/dataset_v1.jsonl` (100 hand-written Korean reports with labels; 26 linked to 12/12 known issues, 11 near misses, 4 injection attempts), `eval/check_dataset.py` distribution tables, `eval/hard_cases.md` (25 hard cases for review), `tests/test_dataset.py`. Awaiting user review before freezing.

## 2026-11-21 Task 7: FastAPI routes and UI
- `app/main.py` (login/logout/me, reports CRUD-ish + reanalyze, chat, chat history, LLMError -> 422/502 Korean detail), `static/` login + triage/chatbot page (textContent only). Store records gain `logs_summary`. 114 tests pass; live manual check ok.

## 2026-11-21 Task 6: multi-turn chatbot
- `app/chat.py`: CHAT_TOOL_DEFS (5 strict tools), dev-scoped `run_chat_tool`, `build_messages` (last 6 + state summary), `summarize_state`, `chat_turn` (tool loop max 5). `prompts/chat.md`; `append_chat` now locked.


## 2026-11-21 Task 5: store, login, assignment
- `app/store.py` Store (R-%04d global IDs, per-dev reports/chat JSONL, shared logs.jsonl linked by request_id, atomic rewrite); `app/auth.py` (developers.json areas, assign -> dev3 fallback, in-memory sessions, 401 dependency, logout). 90 tests pass.

## 2026-11-21 Task 4: prompts and triage pipeline
- `prompts/` Markdown templates (Task/Context/Constraints/Input/Output format/Success criteria) for extract, classify, link, score + few-shot files + score Rubric.
- `app/prompts.py` `build_system` (rules -> examples -> Rubric, cache marker on last block); `app/pipeline.py` `analyze` with PipelineConfig/BASELINE, tool loop (max 4 rounds), re-analysis with confirmed fields + new info.
- Fixed `feature_area` tool schema (anyOf) after the live API rejected enum + type list. Live Haiku run: 3 reports OK, cache hits on every step after the first report.

## 2026-11-21 Task 1: scaffold
- Created venv, requirements.txt, pytest.ini, `app/config.py` (models, prices, paths, `get_api_key`), CLAUDE.md, SPEC/STATE/HISTORY.
