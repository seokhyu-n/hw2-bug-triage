# HISTORY

Newest entry on top.

## 2026-11-21 Task 5: store, login, assignment
- `app/store.py` Store (R-%04d global IDs, per-dev reports/chat JSONL, shared logs.jsonl linked by request_id, atomic rewrite); `app/auth.py` (developers.json areas, assign -> dev3 fallback, in-memory sessions, 401 dependency, logout). 90 tests pass.

## 2026-11-21 Task 4: prompts and triage pipeline
- `prompts/` Markdown templates (Task/Context/Constraints/Input/Output format/Success criteria) for extract, classify, link, score + few-shot files + score Rubric.
- `app/prompts.py` `build_system` (rules -> examples -> Rubric, cache marker on last block); `app/pipeline.py` `analyze` with PipelineConfig/BASELINE, tool loop (max 4 rounds), re-analysis with confirmed fields + new info.
- Fixed `feature_area` tool schema (anyOf) after the live API rejected enum + type list. Live Haiku run: 3 reports OK, cache hits on every step after the first report.

## 2026-11-21 Task 1: scaffold
- Created venv, requirements.txt, pytest.ini, `app/config.py` (models, prices, paths, `get_api_key`), CLAUDE.md, SPEC/STATE/HISTORY.
