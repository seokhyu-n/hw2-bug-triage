# RunBuddy 버그 제보 트리아지 서비스 — 설계 문서

- 작성일: 2026-11-21
- 과제: 부트캠프 1주차 과제 2 "개발팀 업무" (강의자료 65쪽, 공통 조건 68쪽)
- 상태: 승인 대기

## 1. 의도와 이유

부트캠프 1주차 과제 4개 중 하나를 **완벽하게** 해내는 것이 목표다. 강사는 4개를 다 할 필요는 없고 하나를 제대로 한 뒤 시간이 남으면 더 해보라고 했다. 제출 기한은 아직 정확히 모른다.

"완벽"의 기준(제안, 사용자 확인 필요):
1. 68쪽 공통 필수 조건을 **전부** 실제로 동작하게 구현한다.
2. 각 기법의 효과를 **평가 수치로 보여준다**. Baseline에서 시작해 한 번에 한 변수만 바꾼 Run 기록이 남는다.
3. README에 **"기법 → 구현 위치" 대응표**를 둬서 채점자가 바로 찾을 수 있다.

도메인은 사용자가 팀으로 직접 만든 안드로이드 러닝 앱 **RunBuddy**(`C:\Users\maki2\AndroidStudioProjects\RunBuddy-main`)로 정했다. 실제 코드에서 나올 법한 버그를 더미 데이터로 써서 설득력을 높인다. RunBuddy 코드는 읽기만 하고 수정하지 않는다.

## 2. 서비스 한 줄 정의

RunBuddy 사용자·QA가 남긴 버그 제보를 받아 **분류·추출·스코어링**하고, **알려진 이슈와 수정 버전을 조회**해 연결한 뒤, 개발자가 볼 화면에 **연결된 이슈와 부족한 정보**를 정리해 보여주는 웹 서비스.

## 3. 목표 / 비목표 / 반목표

**목표**
- 65쪽 태스크: 분류(버그 / 문의 / 개선 요청), 추출(환경, 앱 버전, 재현 절차), 스코어링(정보 완성도, 우선순위)
- 기존 이슈·수정 버전 조회 기능(더미 JSON), 연결된 이슈와 부족한 정보 표시
- 68쪽 공통 조건 전부(아래 6절 대응표)
- 태스크별 평가 결과 + 개선 히스토리(CSV/Excel, 선택적으로 Claude 아티팩트)

**비목표**
- 비밀번호·권한 체계(로그인은 개발자 ID만 입력), 실제 DB, 배포, 실제 이슈 트래커(GitHub/Jira) 연동
- 챗봇의 정량 평가(평가는 트리아지 태스크에 집중. 챗봇은 시나리오 몇 개로 정성 확인)
- 모바일 앱 화면(구조로만 언급), 화려한 프론트엔드
- RunBuddy 코드 수정

**반목표** (기술적으로 돌아가도 실패로 보는 것)
- 입력에 없는 앱 버전·기기·재현 절차를 모델이 **지어내서** 채우는 것 → 원문에 없으면 반드시 `null` + "부족한 정보"로 표시
- 조회하지 않은 이슈를 "관련 이슈"로 단정하는 것 → 이슈 연결은 도구 조회 결과에 있는 ID만 허용
- 기법을 "썼다고만" 하고 평가로 효과를 보여주지 못하는 것
- API 키가 화면·로그·커밋에 노출되는 것

## 4. 제약

- 위치: `C:\dev\fde\hw2-bug-triage` (수업 규칙: 실습 폴더 `C:\dev\fde`, 가상환경 이름 `venv`, `.env`의 `CLAUDE_API_KEY`)
- Python 3.12(`%LOCALAPPDATA%\Programs\Python\Python312\python.exe`), pip는 항상 `python -m pip`
- Windows, PowerShell. `.env`는 덮어쓰지 않고 `.gitignore`에 포함
- Claude API(공식 `anthropic` Python SDK). 기본 모델 `claude-haiku-5-5`, 비교 모델 `claude-sonnet-5-5`
  - 두 모델 모두 adaptive thinking이 기본으로 켜져 있음. `effort`는 명시적으로 지정(Haiku 5.5 기본값은 medium)
  - Sonnet 5.5는 `tool_choice`의 `any`/`tool` 강제가 400 → 항상 `auto` + 프롬프트 지시 + `strict: true`
  - assistant prefill 불가 → 출력 형식은 Structured Outputs(`output_config.format`)로
  - `stop_reason`이 `refusal`/`max_tokens`인 경우를 처리
- 비용: Haiku 5.5 기준 입력 $0.10 / 출력 $0.50 per MTok. 평가 반복 실행 비용은 매 Run마다 기록

## 5. 접근 방식 (검토한 안)

| 안 | 내용 | 장점 | 단점 |
|---|---|---|---|
| **A. FastAPI 백엔드 + 간단한 웹 페이지 (선택)** | 서버 하나가 JSON API와 정적 HTML/JS 화면을 함께 제공 | 강의 51·52쪽 구조(백엔드가 키·모델·도구 담당, request_id 로그) 그대로. 프론트 부담이 작아 LLM·평가에 집중 | 화면이 소박함 |
| B. Streamlit 단일 앱 | 한 파일로 UI+로직 | 가장 빠름 | 백엔드/화면 분리가 안 보임 → "서비스" 느낌 약함 |
| C. FastAPI + React 분리 | 별도 프론트엔드 | 그럴듯함 | 시간 대부분이 프론트로 감. 과제 핵심과 거리 |

**사용자가 A를 선택**했다. 이유: 강의 구조를 그대로 따르면서 "완벽" 기준(기법 구현 + 평가)에 시간을 가장 많이 쓸 수 있다.

## 6. 필수 조건 대응표 (68쪽)

| 조건 | 구현 위치(예정) |
|---|---|
| LLM API 호출, System·User 분리, 주요 파라미터 | `app/llm.py` 공통 호출 함수. model, system, max_tokens, output_config(effort, format), tools, stop_sequences 설정 |
| Markdown 프롬프트 템플릿 | `prompts/*.md` (Task / Context / Constraints / Input / Output format / Success criteria) |
| Few-shot | 분류·스코어링 프롬프트의 예시 블록 (경계 사례: 버그 vs 문의, 버그 vs 개선 요청, 복합) |
| Decomposition, Prompt Chaining | 파이프라인 4단계, 앞 단계 결과를 다음 호출에 전달 (7절) |
| CoT | 우선순위 판단 단계: 근거(영향 범위·빈도·우회 가능 여부)를 먼저 쓰고 점수를 내게 함 (`reasoning` 필드) |
| Rubric | 정보 완성도 0·1·2점, 우선순위 P1~P4 채점 기준 명시 |
| 정보 부족 시 답변 불가 | 원문에 없는 필드는 `null`, `missing_fields` 목록 + 개발자가 물어볼 질문 생성. 판단 불가 시 `answer_status: need_info` |
| Structured Outputs | 단계마다 JSON Schema를 `output_config.format`으로 전달, Pydantic으로 재검증 |
| Function calling | `search_known_issues`, `get_release_info` 도구 (8절), tool_use → 앱 실행 → tool_result 루프 |
| Context 선별·위치·상태 관리 | 단계별로 필요한 필드만 전달, 재분석 시 "확정 상태 + 새로 추가된 정보"만 전송, 원본 이력은 서버 보관 |
| Prefix cache 고려 배치 | 고정 규칙·Few-shot을 system 앞쪽 + `cache_control`, 제보 원문·조회 결과는 뒤. `usage.cache_read_input_tokens`로 적중 확인 |
| 여러 LLM 태스크 조합 | 추출·분류·이슈 연결·스코어링을 하나의 서비스로 조합 |
| 평가셋·지표 | 입력+정답 평가셋, 태스크별 지표 (10절) |
| Python 자동 채점, CSV·Excel | `eval/run_eval.py` → `eval/results/*.csv`, `runs.xlsx` |
| 품질·응답시간·비용 비교 | Run마다 세 가지를 함께 기록 |
| Baseline 후 한 변수씩 개선 | Run 기록표 (10절) |

## 7. 분석 파이프라인

제보 1건 → `request_id` 발급 → 아래 4단계를 순서대로 호출(Chaining).

1. **추출** (`extract`): 원문에서 `device_model`, `android_version`, `app_version`, `feature_area`(트래킹/지도/기록/카드 이미지/음성/로그인/AI 채팅/기타), `symptom`, `repro_steps[]`, `expected`, `actual`, `frequency`. 원문에 없으면 `null`.
2. **분류** (`classify`): 입력 = 원문 + 추출 결과. `category` ∈ {bug, question, feature_request}, 복합이면 `labels`에 여러 개 + 주 라벨. Few-shot으로 경계 사례를 가르친다.
3. **이슈 연결** (`link`): 입력 = 추출 결과(원문 전체는 보내지 않음 → Context 선별). 모델이 도구로 알려진 이슈와 릴리스 정보를 조회하고, `linked_issue_id`(없으면 null), `match_reason`, `fixed_in`, `user_should_update`(제보자 버전 < 수정 버전)를 낸다. bug가 아니면 이 단계는 건너뛴다.
4. **스코어링** (`score`): 입력 = 추출 + 분류 + 연결 결과.
   - `completeness` 0/1/2 (Rubric: 0 증상 불명확 / 1 증상은 명확하나 재현 절차·환경 중 핵심 누락 / 2 증상·환경·재현 절차 모두 있음). bug가 아니면 null(강의 34쪽 규칙과 동일)
   - `priority` P1~P4 + `reasoning`(CoT). P1 = 크래시·데이터 손실·다수 사용자, P4 = 사소한 표시 문제
   - `missing_fields` + `questions_to_reporter`(부족한 정보를 묻는 질문)

**재분석**: 개발자가 화면에서 빠진 정보(예: 앱 버전)를 입력하면 같은 `request_id`로 다시 분석한다. 이때 이전 원문 전체가 아니라 **확정된 필드 + 새 정보**만 보내 Context를 줄인다.

## 8. 더미 데이터와 도구

`data/known_issues.json` — RunBuddy 코드에서 근거를 찾은 이슈 약 10~15건. 예:
- 알림 채널을 API 26 미만에서 생성 → Android 7.x에서 러닝 시작 시 크래시
- Android 14에서 위치용 포그라운드 서비스 타입 누락 → 러닝 시작 시 크래시
- 위치 요청 간격 100ms → 배터리 급감
- 30m 초과 이동 무시 → 신호 약한 곳에서 거리 과소 측정
- 체중 70kg 고정 → 칼로리 부정확
- (그 외 지도·기록·카드 이미지·TTS·로그인 관련)

각 이슈: `id`, `title`, `feature_area`, `symptoms[]`, `affected_android`, `affected_app_versions`, `status`(open/fixed), `fixed_in`, `workaround`.

`data/releases.json` — 가상의 릴리스 1.0 → 1.0.1 → 1.1.0 → 1.1.1 → 1.2.0, 각 버전에 고친 이슈 ID 목록.

도구 (Function calling):
- `search_known_issues(feature_area?, keywords[], android_version?, app_version?)` → 후보 이슈 최대 5건, 결과 없음이면 `{"status": "not_found"}`
- `get_release_info(version)` → 해당 버전의 수정 내역, 없으면 `not_found`

도구 정의는 `strict: true`. 도구 실행 오류는 `is_error: true`로 돌려준다.

## 9. 웹 서비스

사용자가 정한 형태: **트리아지 화면 + 개발자 ID 로그인 + 멀티턴 챗봇** (수업 실습의 "ID 로그인 + 사용자별 DB + 멀티턴 챗봇 + 짧은 기억" 구조를 과제 2에 맞춘 것).

**로그인과 상태**
- 첫 화면은 로그인. 개발자 ID(예: `dev1`, `dev2`)만 입력한다. 비밀번호 없음.
- 로그인한 ID가 상태값이 된다. 제보는 접수 시 담당 개발자 ID가 붙고, 각 개발자는 **자기 담당 제보와 대화만** 보고 조회할 수 있다(도구도 이 ID로 필터).
- 더미 개발자 2~3명, 담당 영역(예: dev1 = 트래킹·서비스, dev2 = 지도·기록·카드 이미지)을 `data/developers.json`에 둔다. 담당자는 추출된 `feature_area`로 자동 배정(제안).

**멀티턴 챗봇** (개발자용, 트리아지 결과 옆)
- 개발자가 자연어로 묻고 지시한다. 예: "R-0007이랑 비슷한 이슈 더 있어?", "P1만 보여줘", "R-0007 제보자 앱 버전은 1.0이래".
- 챗봇 도구(Function calling): `search_known_issues`, `get_release_info`, `list_my_reports(priority?, category?)`, `get_report(request_id)`, `reanalyze_report(request_id, added_info)`
  - `reanalyze_report`는 7절 재분석과 같은 경로를 탄다(확정 필드 + 새 정보만 전달).
- **짧은 기억**: 최근 N턴(예: 6턴)만 그대로 보내고, 그보다 오래된 부분은 "확정 상태 요약"(지금 보고 있는 제보 ID, 확정된 사실, 미해결 질문)으로 대체한다. 원본 대화는 서버에 전부 보관.
- **Prefix cache 배치**: [고정 system 규칙 + 도구 정의 + Few-shot] → [개발자 ID·확정 상태 요약] → [최근 대화] → [이번 질문] 순서. 앞쪽은 매 턴 바이트 단위로 같게 유지.
- 대화는 Anthropic SDK의 tool_use / tool_result 루프로 직접 구현(프레임워크 없음).

**API**
- `POST /api/login` → 개발자 ID 확인, 세션 쿠키(서버 메모리)
- `POST /api/reports` → 제보 접수 + 분석 실행, `request_id`와 결과 반환
- `POST /api/reports/{request_id}/reanalyze` → 추가 정보로 재분석
- `GET /api/reports/{request_id}` → 결과 조회(담당자만)
- `GET /api/reports` → 내 처리 목록(우선순위 정렬)
- `POST /api/chat` → 챗봇 한 턴
- `GET /` → 로그인 화면, `/app` → 트리아지 + 챗봇 화면

**저장**: 결과, 대화, 단계별 로그(토큰·지연·비용·캐시 적중)를 `data/runtime/` 아래 개발자별 JSONL로 저장(제안. DB는 비목표).

**화면 스케치**

로그인 후 화면은 왼쪽에 아래 트리아지 패널(위: 내 제보 목록, 아래: 선택한 제보 상세), 오른쪽에 챗봇 패널을 둔다.

```
┌ RunBuddy 버그 제보 트리아지 ───────────── dev1 [로그아웃] ┐
│ [제보 내용 입력 ...................................]       │
│ [분석하기]                                                │
├─────────────────────────────────────────────────────────┤
│ #R-0007  분류: 버그 (주)  ·  우선순위 P1  ·  완성도 1/2   │
│ 추출  기기: Galaxy S23 | Android: 14 | 앱 버전: (없음)    │
│       기능: 러닝 트래킹 | 증상: 시작 누르면 앱 종료         │
│       재현: 1) 로그인 2) 달리기 시작 터치                  │
│ 관련 이슈  ISSUE-02 Android 14 FGS 타입 누락 → 1.0.1 수정 │
│ 판단 근거  크래시 + 최신 OS 사용자 전체 영향 → P1          │
│ 부족한 정보  앱 버전                                      │
│   → "설정 > 앱 정보에서 RunBuddy 버전을 알려주세요"         │
│ [앱 버전 입력: ____ ] [다시 분석]                         │
│ 처리 시간 3.1s · 비용 $0.0004 · 캐시 적중 1,210 토큰       │
└─────────────────────────────────────────────────────────┘
```

제보 출처(사용자 원문)와 도구 조회 사실은 화면에서 구분해서 표시한다.

## 10. 평가

**평가셋 `eval/dataset_v1.jsonl`** (100건, 고정 후 변경 금지 — 수업 실습과 같은 규모. 그중 가장 어렵고 애매한 사례 10건 이상은 `hard: true`로 표시하고 아티팩트로 따로 정리)
- 강의 54쪽 방식: 고성능 모델(Sonnet 5.5)로 입력+정답 초안 생성 → 사람이 검토 → 생성 프롬프트 개선
- 구성: 정상 사례, 경계 사례(버그인지 문의인지 애매함, 버그+개선 요청 복합), 정보 누락 사례, 알려진 이슈와 일치하는 사례, 일치하지 않는 사례
- 정답 필드: category(+labels), 추출 필드, completeness, priority, linked_issue_id

**지표** (55쪽)
| 태스크 | 지표 |
|---|---|
| 분류 | Accuracy, Macro F1 |
| 추출 | 필드별 정확도, 누락·오추출 비율(지어낸 값 = 오추출) |
| 스코어링 | completeness MAE, priority 정확 일치율 / ±1 이내 비율 |
| 이슈 연결 | 정확도(없음=null 포함) |
| 공통 | 건당 평균 응답시간, 건당 비용, 캐시 적중 토큰 |

**실행**: `python eval/run_eval.py --run-id Run-01 --model claude-haiku-5-5 --prompt-version v1 --change "변경사항 설명"` → 건별 결과 CSV + `eval/runs.csv`에 한 줄 추가(57쪽 형식: 날짜, Run ID, 모델, 프롬프트 버전, 지표, 평균 응답시간, 총비용, 변경사항). 정답은 채점에만 쓰고 모델에는 Input만 보낸다. 분류는 Run마다 **Confusion matrix**도 저장(`eval/results/<run>_confusion.csv`).

**정성 평가**: Run마다 틀린 사례를 정리한 분석용 아티팩트를 만든다(수업 실습 방식). 예: 정답이 있는데 `null`로 예측하는 "지나친 보수성" 같은 실패 유형을 찾아 다음 Run의 변수로 고른다.

**실험 순서** (한 번에 한 변수, 61쪽의 3개 실험 포함)
| Run | 바꾸는 것 | 고정 |
|---|---|---|
| Run-01 Baseline | 지시문만, Few-shot·Rubric 없음, 전체 원문을 모든 단계에 전달, Haiku | 평가셋 |
| Run-02 | Few-shot 추가 (61쪽 실험 2) | 나머지 |
| Run-03 | Rubric 추가 | 나머지 |
| Run-04 | Context 선별 (61쪽 실험 3) | 나머지 |
| Run-05 | 모델 Haiku ↔ Sonnet 비교 (61쪽 실험 1) | 나머지 |
| Run-06+ | 실패 유형을 보고 고른 개선 1개씩 | 나머지 |

최종 산출물: `eval/runs.xlsx`(Run 기록 + 태스크별 지표 + 개선사항), 원하면 Claude 아티팩트 표.

**분석용 아티팩트** (수업 실습과 같은 종류)
1. Chaining 흐름과 단계별 프롬프트 구조 다이어그램
2. Function calling 워크플로우 다이어그램
3. 서비스 전체 워크플로우·컨텍스트 엔지니어링·프롬프트 배치 정리
4. 평가: 어려운 사례 10건, Run별 지표 비교, 틀린 사례 정성 분석

## 10-1. 수업 규칙 반영 (2026-11-21 실습 문서 기준)

- 프레임워크(LangChain 등) 없이 Anthropic SDK만으로 "날것으로" 구현한다.
- 프로젝트 `CLAUDE.md`에 "개발 중 API 호출은 Haiku 5.5만 사용, 예외는 평가의 모델 비교 Run(Sonnet 5.5) 하나" 규칙을 둔다.
- 강의 부록 방식대로 `docs/SPEC.md`, `docs/STATE.md`, `docs/HISTORY.md`를 두고 `CLAUDE.md`에서 관리 규칙을 정한다.
- Windows 실행법은 README에 `venv\Scripts\activate` 기준으로 쓴다.

## 11. 프로젝트 구조 (제안)

```
C:\dev\fde\hw2-bug-triage\
  venv\                 (gitignore)
  .env                  CLAUDE_API_KEY=...  (gitignore)
  .gitignore
  requirements.txt
  README.md             실행법 + 기법 대응표 + 평가 요약
  app\
    main.py             FastAPI 라우트
    llm.py              Claude 호출 공통 함수(로그·비용·캐시 기록)
    pipeline.py         extract → classify → link → score
    chat.py             멀티턴 챗봇(짧은 기억, tool 루프)
    auth.py             개발자 ID 로그인·세션
    tools.py            도구 정의 + 실행
    schemas.py          Pydantic 모델 / JSON Schema
    store.py            request_id 결과·로그 저장
  prompts\              단계별 Markdown 템플릿 + few-shot
  data\known_issues.json, releases.json, runtime\
  static\index.html, app.js, style.css
  eval\dataset_v1.jsonl, run_eval.py, grade.py, results\, runs.csv
  tests\                파이프라인·채점 함수 단위 테스트(LLM은 목 처리)
  docs\superpowers\specs\  (이 문서)
```

## 12. 빌더에게 맡기는 것 / 내가 정한 것

**사용자가 정한 것**: 과제 2(개발팀 업무), 도메인 RunBuddy, 목표 "하나를 완벽하게", 접근 A(FastAPI + 간단한 웹), 서비스 형태 "트리아지 + 개발자 ID 로그인 + 멀티턴 챗봇", 모델은 개발·서비스 모두 Haiku 5.5이고 Sonnet 5.5는 평가의 모델 비교 Run에서만 사용.

**작성자(Claude)가 정한 것 — 사용자 확인 대상**
- "완벽"의 3가지 기준(1절)
- 폴더 `C:\dev\fde\hw2-bug-triage`, `venv`, `CLAUDE_API_KEY`
- 기본 모델 Haiku 5.5, 비교 Sonnet 5.5
- 4단계 파이프라인 순서와 단계별 입력
- 우선순위 P1~P4, 완성도 0~2
- 저장은 JSONL 파일
- 평가셋 100건(어려운 사례 10건 이상), Run 순서
- 평가셋 정답 검토: Claude가 초안을 만들고, 사용자는 어려운 사례 10건을 중심으로 표에서 훑어보며 틀린 정답만 고친다
- 담당 개발자 자동 배정 규칙, 짧은 기억의 턴 수(6턴)
- 제보·프롬프트·화면은 한국어. 모델 프롬프트의 규칙 부분은 한국어로 쓰되, 토큰이 아쉬우면 평가로 영어 버전을 비교하는 Run을 추가할 수 있음
- Prefix cache: 모델별 최소 캐시 길이보다 고정 부분이 짧으면 캐시가 안 걸린다. `cache_read_input_tokens`로 실제 적중을 확인하고, 안 걸리면 그 사실과 이유를 README에 그대로 적는다(억지로 프롬프트를 늘리지 않음)
- 로컬 git 저장소로 관리하고 단계마다 커밋. 원격(GitHub) push는 사용자가 요청할 때만

**빌더 재량**: 화면 스타일, 파일 내부 구조, 평가 리포트 형식의 세부, 테스트 범위
