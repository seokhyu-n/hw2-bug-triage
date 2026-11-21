# HISTORY

Newest entry on top.
## 2026-11-22 Task 10: baseline and one-variable experiments
- Runs (Haiku unless noted, 100 cases, 0 errors): Run-01 baseline / Run-02 +few-shot / Run-03 +rubric / Run-04 +context select (default) / Run-05 Sonnet / Run-06 extract feature_area for non-bugs / Run-07 rubric P1 rule. Total spend ~$2.11 (Sonnet $1.57).
- Ablation: rubric had the biggest effect on scoring (completeness MAE 0.34 -> 0.18), context select cut MAE to 0.11 at lower cost; few-shot helped priority but caused 2 bug over-classifications (E-021, E-052).
- Improvement 1 (Run-06, kept): all 13 Run-04 feature_area misses were non-bug reports (prompt tied it to the symptom); extraction 0.950 -> 0.972, miss rate 0.068 -> 0.005, hallucination 0.018 -> 0.025 (2 null cases filled as `other`).
- Improvement 2 (Run-07, kept): rubric no longer lets "unknown scope" demote a confirmed crash/login failure/record loss; priority exact 0.84 -> 0.88, P1 recall 10/16 -> 15/16, one new over-rating (E-065). No change reverted.
- Final setting: Haiku 5.5 + few_shot + rubric + context_select + both fixes (Run-07). Quality first: classification/extraction/link equal to or better than Sonnet (Run-05); Sonnet is better only on priority (0.93 vs 0.88) and completeness MAE (0.04 vs 0.11) at ~18x cost ($1.57 vs $0.087 / 100) and +35% latency (10.9s vs 8.1s), so Haiku. Sonnet with the improved prompts was not run.
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
