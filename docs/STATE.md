# STATE

Branch: feat/triage-service

## Done
- Task 1-3: scaffold/config, dummy issues/releases + tools (`app/tools.py`), schemas + `call_llm` (cost/cache logging)
- Task 4: prompts (`prompts/*.md`) + 4-step pipeline; code enforces link IDs from tool results, fixed_in from
  tool data, missing_fields computed (empty for non-bugs), completeness=None for non-bugs, need_info rule
- Task 5: per-developer JSONL store (`app/store.py`), ID login + auto-assignment (`app/auth.py`)
- Task 6: multi-turn chatbot (`app/chat.py`), last 6 messages + `[상태 요약]`, dev-bound tools, max 5 rounds
- Task 7: FastAPI app (`app/main.py`) + plain HTML/JS UI (`static/`); manual API check ok, browser check pending (user)
- Task 8: `eval/dataset_v1.jsonl` 100 cases (bug 56 / question 22 / feature 22, hard 25, 12/12 issues linked),
  `eval/check_dataset.py` (distribution tables), `eval/hard_cases.md`, `tests/test_dataset.py`; 124 tests pass

## Prefix cache (live, Haiku 5.5)
- cache_read > 0 from the 2nd report on (extract 3364, classify 2152, link 2542, score 3820 tokens).

## Next
- Task 8 step 5: user reviews `eval/hard_cases.md`; apply fixes, then freeze dataset_v1 (later changes -> v2)
- Task 9 per plan `docs/superpowers/plans/2026-11-21-runbuddy-bug-triage.md`
- User: open http://127.0.0.1:8000 to check the UI (`venv\Scripts\python.exe -m uvicorn app.main:app --port 8000`)

## Notes
- `.env` holds the real key; never read it.
- Dataset labels: versions as digits only ("v1.0.1" -> "1.0.1", "최신"/One UI -> null); non-bugs P4, completeness null.
