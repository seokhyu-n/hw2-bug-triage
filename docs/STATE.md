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

## Prefix cache (live, Haiku 5.5)
- cache_read > 0 from the 2nd report on: extract 3364, classify 2152, link 2542 (tools+system),
  score 3820 tokens. Minimum cacheable prefix on Haiku 5.5 is 512, so no padding needed.
- Live check of 3 reports: about $0.003 per batch of 3 (crash $0.0014, question $0.0004, vague $0.001).

## Next
- Task 5 per plan `docs/superpowers/plans/2026-11-21-runbuddy-bug-triage.md`

## Notes
- `.env` holds the real key; never read it.
- Re-analysis path is unit-tested only (not yet live-checked).
