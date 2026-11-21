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
  `eval/check_dataset.py` (distribution tables), `eval/hard_cases.md`, `tests/test_dataset.py`
- Task 9: `eval/grade.py` + `eval/run_eval.py` (`-m eval.run_eval --run-id X [--baseline|--no-*] --change ".." --workers 4`); smoke run `Run-00-smoke` kept
- Task 10: Run-01..07 (baseline -> +few-shot -> +rubric -> +context select -> Sonnet -> 2 prompt fixes), total ~$2.11;
  final = Haiku default + extract feature_area fix + rubric P1 rule (Run-07); `docs/analysis/run_comparison.md`, `error_analysis.md`; 137 tests pass

## Prefix cache (live, Haiku 5.5)
- cache_read > 0 from the 2nd report on (extract 3364, classify 2152, link 2542, score 3820 tokens).

- Task 11: `README.md` (technique map, Run table, cache, security, limits), `docs/artifacts/*.html` x4 (chaining, function_calling, service_workflow, evaluation), `requirements.lock.txt`; 137 tests pass, server boot checked

## Next
- Controller: publish the 4 artifacts, fill the placeholder links in README "분석 아티팩트"
- Next improvement candidates: rubric core-feature scope (P3->P2 over-rating), link rule app_version >= fixed_in -> no link
- User: open http://127.0.0.1:8000 to check the UI (`venv\Scripts\python.exe -m uvicorn app.main:app --port 8000`)

## Notes
- `.env` holds the real key; never read it.
- Dataset labels: versions as digits only ("v1.0.1" -> "1.0.1", "최신"/One UI -> null); non-bugs P4, completeness null. dataset_v1 frozen.
