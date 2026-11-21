# STATE

Branch: feat/triage-service

## Done
- Task 1: scaffold, config, CLAUDE.md
- Task 2: dummy issues/releases + lookup tools (`app/tools.py`)
- Task 3: schemas + `call_llm` wrapper with cost/cache logging
- Task 4: prompt templates (`prompts/*.md`) + 4-step pipeline (`app/prompts.py`, `app/pipeline.py`)
  - link step sends tools + Link schema on every call (live API accepts both together)
  - code enforces: link ID must come from tool results, fixed_in from tool data,
    user_should_update = version_lt, missing_fields computed (empty for non-bugs),
    completeness=None for non-bugs, answer_status need_info only for bugs with 2+ of
    app_version/android_version/repro_steps missing
  - fixed Task 2 tool schema: feature_area enum now anyOf (live API 400'd on enum + type list)
- Task 5: per-developer JSONL store (`app/store.py`), ID login + auto-assignment (`app/auth.py`)
  - Store(base_dir); reports.jsonl rewritten atomically; logs.jsonl one line per step with request_id
- Task 6: multi-turn chatbot (`app/chat.py`, `prompts/chat.md`, `build_chat_system` in prompts.py)
  - history = last 6 messages verbatim + code-built `[상태 요약]` prepended to first user msg; stored chat is plain text only
  - report tools bound to dev_id (others get not_found); tool loop max 5 rounds; append_chat now under _LOCK
  - live (Haiku): 3-turn scenario ok (list_my_reports, search_known_issues, reanalyze_report P1 -> P2); cache_read 2478/4956/4956
- Task 7: FastAPI app (`app/main.py`) + plain HTML/JS UI (`static/`), 114 tests pass
  - routes: login/logout/me, reports (post/list/get/reanalyze), chat, chat/history; static at `/`, `/app`
  - store records now carry `logs_summary` (latency/cost/cache_read of latest analysis); old records default to zeros
  - UI reanalyze passes dev-typed added_info straight to `analyze` (no injection guard; guard is chat-only)
  - manual: uvicorn + Invoke-RestMethod login -> report (P1, ISSUE-02) -> get -> chat (list_my_reports) ok; browser check pending (user)

## Prefix cache (live, Haiku 5.5)
- cache_read > 0 from the 2nd report on (extract 3364, classify 2152, link 2542, score 3820 tokens).

## Next
- Task 8 per plan `docs/superpowers/plans/2026-11-21-runbuddy-bug-triage.md`
- User: open http://127.0.0.1:8000 in a browser to check the UI (`venv\Scripts\python.exe -m uvicorn app.main:app --port 8000`)

## Notes
- `.env` holds the real key; never read it.
- Re-analysis path now live-checked via chatbot reanalyze_report.
