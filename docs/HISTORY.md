# HISTORY

Newest entry on top.
## 2026-11-24 Ideas from running apps' support (NRC, Strava, Runkeeper, MapMyRun)
- Public known-issues page `/known-issues` + `GET /api/public/issues` (public fields only; title = first symptom in users' words; open first; "N reports") and a banner on the report page.
- Device self-check guides (`data/self_help.json`, `app/self_help.py`): Galaxy app-sleep steps, iPhone Low Power/location/background refresh, GPS-fix tips; shown before submitting (not for questions or crashes) and as a "기기 설정 원인 가능성" hint for developers.
- Run record attached to a report (`app/activity.py`, `data/sample_activities.json` for the demo): validated summary -> `[연결된 러닝 기록]` block + developer card; `/report?activity_id=A-1002`.
- Live: Galaxy "화면 끄면 기록이 끊겨요" + A-1002 -> guide shown first, then the AI wrote "GPS 위치 없는 구간 9분 15초" into actual; developer saw card + hint. 253 tests pass.
## 2026-11-24 Link rule: no link when the reporter already has the fixed version
- `_finalize_link`: app_version >= issue fixed_in -> no link (regression / new cause stays a new report). Measured first on saved V2-Run-11 x3 results (post-processing, no cost): link 0.967 -> 0.983 in all three (E-043, E-049), no correct link removed. V2-Run-12 live ($0.105): link 0.992 (only E-090, version "최신" = null), cls 0.983, priority 0.925, MAE 0.092, v1 missed bugs 0. Current setting = V2-Run-12. 2 tests added (234 pass).
## 2026-11-24 iPhone support in the analysis + final setting repeated 3x
- Extraction gets `platform` (android/ios) and `ios_version` (defaults keep old saved results loadable); missing_fields / need_info use the OS-specific version (`pipeline.os_version_field`); prompts say Android·iOS, rubric "환경" = OS version + app version, extract few-shot adds an iPhone example; iPhone reports are never linked to Android-only issues (prompt + `_finalize_link`). Dev screen shows iOS version; chat detail includes platform.
- V2-Run-11 x3 on dataset_v2 ($0.32): cls 0.975 (0.967-0.983), priority 0.928 (0.900-0.958), new-20 priority 0.95-1.00, extraction 0.974, MAE 0.129 (0.108-0.154, probably slightly worse than Run-07's 0.071-0.109), link 0.967 (E-043/049/090 regression-link pattern). v1/v2 labels unchanged (platform/ios_version not labelled there).
- New `eval/dataset_ios.jsonl` (9 iPhone + 1 Android control) via `feature_evals ios` (FE-IOS-01): everything 10/10, no iOS version in android_version, none invented. FE-SHOT-02 / FE-REPLY-02 re-run after the schema change: same results. Live: iPhone report R-0010 -> platform ios, missing ios_version, AI asks for the iOS version.
## 2026-11-24 Phone list: 갤럭시 / 아이폰 only
- User decision: the report page offers only Galaxy and iPhone. `static/devices.json` now has galaxy (27, os android) and iphone (22, os ios); other makers removed (typed names go through "목록에 없어요"). Choosing 아이폰 relabels the version box "iOS 버전" and sends `ios_version` (new optional form field, composed as "- iOS 버전"), so it never reads as an Android version; suggestions skip Android rules for iOS.
- Known limit: pipeline, known issues and eval set are Android-only; an iPhone report has `android_version` null and may show as need_info.
## 2026-11-24 Phone maker/model dropdowns on the report page
- `static/devices.json` (Samsung/Google/Xiaomi/LG, ~45 models + "기타 제조사"); report page: maker -> model selects, "목록에 없어요" or other maker shows a text box; a typed name gets the family prefix (갤럭시/픽셀/...). Hidden `device_model` keeps the API unchanged. App URL prefill selects the model or falls back to other + text. Checked in the browser (no submission); test for the list.
## 2026-11-24 One analysis page only
- Before deleting the 4 single-tab artifacts, compared them with the combined page: same content, but the Function calling tab still said 5 tools (no `assign_report`) and the chain tab lacked the V2-Run-08/10 prompt rules and screenshot/log input. Fixed both sources, rebuilt, republished the combined page (v8), then deleted the 4 pages at the user's request. README/STATE now point to the combined page only.
## 2026-11-24 Run-08..10 and feature evals
- V2-Run-08 (rubric core/aux feature scope): new-20 priority 0.55 -> 0.80, all 0.825 -> 0.892. V2-Run-09 (classify: current normal behaviours) fixed E-101/107/108 but turned 3 real v1 bugs into question/request (E-016, E-020, E-093) -> rejected. V2-Run-10 (exception limited to listed behaviours, "if possibly broken -> bug"): cls 0.975, priority 0.925, v1 missed bugs 0, new-20 cls 0.90 / priority 1.00. MAE 0.141 (noise range). Final service setting. ~$0.33. `docs/analysis/run_08_10.md`.
- `eval/feature_evals.py`: suggest 24/26, 0 wrong; screenshots 9/9 visible, 0/21 invented, injection ignored; reply 16/16, 0/8 invented, class kept 8/8. Excel sheet "추가 기능 평가". Pillow added (draws test screenshots).
- Mistakes on the way: a dry-run command accidentally ran 3 screenshot cases (~$0.01); the first "cropped" test image was not cropped (fixed the image, not the model); a CSV writer bug lost one screenshot run (~$0.01) - fixed + test.
## 2026-11-24 Team triage features
- Same-symptom groups (`app/similar.py`: same tracked issue, or same feature area + char-bigram cosine >= 0.2 with fixed corpus weights; 16/20 same-issue pairs, 4/67 wrong in-area pairs on dataset_v2). Own IDs shown, other developers' only as a count; 3+ at P3/P4 shows a "review priority" hint.
- Team-registered known issues (`app/issues.py`, `data/runtime/_issues.json`) feed the link tool and pre-submit suggestions via `tools.set_extra_issues`; the eval runner never sets it. Resolve an issue -> every open report under it becomes resolved with an update message on the reporter's page (dummy issues get an override, the data file is untouched).
- Reassign (`POST /api/reports/{id}/assign`, history kept, status link kept) + chat tool `assign_report` guarded like reanalyze (receiver must be named in the developer's current message).
- Rate limits on public endpoints (`app/ratelimit.py`), 20 s auto refresh + new-P1 banner/title/notification on the developer page.
- Live: ISSUE-02 group of 3 resolved as 1.2.0 -> R-0006's reporter page shows 수정 완료 + message; new P1 R-0009 raised the alert within 20 s.
## 2026-11-24 Report form like real services (7 items)
- Researched real report screens (Discord bug form, Samsung Members, Google feedback, Instabug, GitHub issue forms, Kakao, Strava) and added: category choice, steps/expected/actual/frequency, device/Android/app version (prefilled from the app's URL), pre-submit known issue + FAQ suggestions, screenshot redaction (+ JPEG EXIF strip), log file, reporter status page with replies, developer processing state + message.
- Design: fields are optional and folded into the report text (`app/report_form.py`), so the same 4-step analysis and the eval set are unchanged; category is passed "for reference" only. Log tail (4,000 chars) and screenshots go to extract only, as data.
- `app/suggest.py`: char-bigram TF-IDF + version rules (no LLM). On dataset_v2: 24/26 linked reports get the right issue, 0 wrong; FAQ never shows on pure bugs. `data/faq.json` is dummy data grounded in the eval questions.
- Status link `/status/<token>` (unguessable; token hidden from dev APIs). Replies saved first, re-analyzed in the worker (resumed on restart), 5 per report. Workflow states new/in_progress/resolved/wont_fix; closed reports take no replies.
- Live check found a race: submitting right after saving a redaction uploaded the original. Fixed (submit waits for the save); verified the stored image is blacked out. Full loop checked live: vague report -> 3 questions -> reporter answer -> re-analysis filled app/device/Android, questions cleared -> dev status + message shown to the reporter. 211 tests pass.
## 2026-11-24 Screenshot attachments on reports
- Reporter page: attach up to 3 images (5 MB each, PNG/JPG/WEBP/GIF) or paste a capture with Ctrl+V; thumbnails with remove. `POST /api/intake` accepts multipart (`text` + `files`) as well as JSON.
- `app/attachments.py`: type by magic bytes (renamed HTML rejected), safe display names, limits. Store saves files under server-made names in `data/runtime/_attachments/<id>/`; the record keeps name/type/size.
- `app/pipeline.py`: images go to the extract step only, before the text; screenshot rules are in the user message, so system prompt, cache and text-only eval runs are unchanged. Re-analysis does not resend images.
- Developer screen: thumbnails (click for full size) via `GET /api/reports/{id}/attachments/{n}` for the assignee only (dev3 for queued); nosniff + CSP headers. Chat `get_report` reports the screenshot count.
- Live check: text without a version + drawn screenshot (app info "버전 1.1.1" + crash dialog) -> app_version 1.1.1 and the dialog text extracted, device/Android left null; dev1, P1, $0.0029, 14.8 s. 191 tests pass.
## 2026-11-24 Intake saves first, analysis runs in the background
- Problem: `POST /api/intake` analyzed before saving, so an API failure dropped the report and the reporter waited ~12 s.
- `app/store.py`: intake queue in `data/runtime/_intake/` (`enqueue`, `queued`, `get_queued`, `set_queue_status`, `complete` moves a report to its developer keeping its ID). `app/intake.py:IntakeWorker`: one background thread, retries transient errors after 5 s / 30 s (3 tries), refusal/truncation fail at once; failed reports stay in the queue; pending ones resume on server start.
- `app/main.py`: intake enqueues and returns the receipt at once; dev3 (fallback) sees pending/failed reports and can call `POST /api/reports/{id}/retry`. `static/app.js`: 분석 중 / 분석 실패 badges and a retry button.
- Verified live: receipt in 0.02 s, bug report analyzed in the background (~17 s) and assigned to dev1 as P1 with ISSUE-02; failed-report screen checked with a temporary entry (removed). 174 tests pass.
- Also: set up on a second PC at `C:\Users\hi\부트캠프\hw2-bug-triage`.
- Analysis page: service tab 1 (flow) and 2 (new bullet: intake/analysis split, retries, failed reports, resume) updated in `service_workflow.html`, combined page rebuilt, both artifacts republished (combined v4, service page v3).
## 2026-11-22 Eval strengthening: repeats, human label review, dataset_v2
- Repeat runs: Run-04 x3 (at commit 988c4a5 via a temporary worktree) and Run-07 x3. Priority exact 0.823 -> 0.880 and extraction 0.949 -> 0.973 hold across all repeats; completeness MAE swings 0.071-0.179 within one setting.
- Human review in chat (no Excel at hand): 56 labels (36 from v1 + 20 new) checked, 0 fixes. E-024 note: 3-second countdown already exists in RunBuddy (kept as feature_request).
- dataset_v2 = v1 + 20 hard classification cases. V2-Run-01 (baseline) vs V2-Run-07 (final): overall final still better on priority/MAE, but worse on the new 20 (classification 0.90 vs 0.80, priority 0.80 vs 0.55): question->bug and P3->P2 over-rating. Docs: `docs/analysis/eval_strengthening.md`, README, evaluation tab 8. Excel gains 반복 실행 and dataset_v2 sheets. Cost ~$0.59.
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
