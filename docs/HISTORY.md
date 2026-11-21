# HISTORY

Newest entry on top.
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
