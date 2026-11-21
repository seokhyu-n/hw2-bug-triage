# RunBuddy 버그 제보 트리아지 서비스 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** RunBuddy 버그 제보를 추출·분류·이슈 연결·스코어링하는 FastAPI 웹 서비스(개발자 ID 로그인 + 멀티턴 챗봇)와, 그 효과를 Baseline부터 한 변수씩 증명하는 평가 도구를 만든다.

**Architecture:** `app/llm.py` 한 곳에서 Anthropic SDK를 호출하고 토큰·지연·비용·캐시를 기록한다. `app/pipeline.py`가 4단계 Chaining(extract → classify → link(Function calling) → score)을 수행하며, 각 기법(Few-shot, Rubric, Context 선별)은 `PipelineConfig` 플래그로 켜고 끌 수 있어 평가 Run에서 한 변수씩 바꿀 수 있다. 웹(`app/main.py`)과 챗봇(`app/chat.py`), 평가(`eval/run_eval.py`)는 모두 같은 파이프라인을 쓴다.

**Tech Stack:** Python 3.12, FastAPI(`fastapi[standard]`), `anthropic` SDK, Pydantic v2, python-dotenv, pytest, openpyxl, 정적 HTML/JS.

**Spec:** `docs/superpowers/specs/2026-11-21-runbuddy-bug-triage-design.md` (실행자는 이 계획과 함께 반드시 읽을 것)

## Global Constraints

- 프로젝트 루트: `C:\dev\fde\hw2-bug-triage`, 가상환경 폴더 `venv`, Python `%LOCALAPPDATA%\Programs\Python\Python312\python.exe`
- pip는 항상 `python -m pip` (예: `venv\Scripts\python.exe -m pip install ...`)
- API 키는 `.env`의 `CLAUDE_API_KEY`. `.env`가 이미 있으면 절대 덮어쓰지 않는다. 키 값은 출력·로그·커밋 금지
- 모델: 개발·서비스·테스트 실호출은 전부 `claude-haiku-5-5`. 유일한 예외는 평가 모델 비교 Run의 `claude-sonnet-5-5`
- LangChain 등 프레임워크 금지. Anthropic SDK를 직접 사용
- `tool_choice`는 항상 `auto`(Sonnet 5.5는 `any`/`tool` 강제가 400). 도구 정의는 `strict: true`
- assistant prefill 금지. 구조화 출력은 `output_config={"format": {"type": "json_schema", "schema": ...}, "effort": ...}`
- 응답의 `stop_reason`이 `refusal`/`max_tokens`이면 예외로 처리하고 화면에 사용자용 메시지로 표시
- tool 루프에서는 `response.content` 블록 전체(thinking 블록 포함)를 그대로 다음 요청에 덧붙인다
- 가격(USD per MTok): Haiku 5.5 입력 0.10 / 출력 0.50 / 캐시 쓰기 0.125 / 캐시 읽기 0.01, Sonnet 5.5 입력 2.00 / 출력 10.00 / 캐시 쓰기 2.50 / 캐시 읽기 0.10
- 열거값: `category` ∈ {`bug`, `question`, `feature_request`}; `feature_area` ∈ {`tracking`, `map`, `record`, `card_image`, `voice`, `login`, `ai_chat`, `other`}; `completeness` ∈ {0,1,2} 또는 null(bug 아님); `priority` ∈ {`P1`,`P2`,`P3`,`P4`}
- 제보 ID 형식 `R-0001`부터 증가. 이슈 ID `ISSUE-01` 형식
- 짧은 기억: 최근 6턴(사용자+어시스턴트 한 쌍 = 1턴)만 원문 전송, 나머지는 상태 요약
- 파일 인코딩: 소스·JSON·JSONL은 UTF-8(BOM 없음), Excel에서 열 CSV는 `utf-8-sig`
- 한국어: 프롬프트 규칙, 화면, 평가 데이터
- 평가셋 100건은 이 세션의 Claude Code가 직접 작성(API로 생성하지 않음 → "Haiku만" 규칙과 충돌 없음)
- 커밋은 작업마다, 원격 push 금지. 커밋 메시지 끝에 `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`

## Review Focus

1. **정보가 없는 제보**("앱이 이상해요" 한 줄) → 추출 필드를 지어내지 않고 전부 null, `missing_fields`와 질문이 채워져야 한다. → Task 4 `test_extract_vague_report_keeps_nulls`(목 응답 검증) + Task 9 평가셋에 해당 사례 포함
2. **다른 개발자의 제보에 접근**(URL에 남의 `request_id`, 챗봇에 "R-0003 보여줘") → 404/"찾을 수 없음", 존재 여부도 노출하지 않음. → Task 5 `test_get_report_other_dev_404`, Task 6 `test_chat_tool_cannot_read_other_dev_report`
3. **앱 버전 표기 흔들림**(`1.0`, `v1.0.1`, `1.0.1 버전`, `최신`) → 비교 가능한 건 정규화, 불가능한 건 None 처리하고 오류 없이 진행. → Task 2 `test_parse_version_variants`
4. **모델이 거절하거나 잘림**(`refusal`, `max_tokens`) → 500이 아니라 사용자 메시지와 함께 422/502로 응답, 로그 기록. → Task 3 `test_call_raises_on_refusal`, Task 7 `test_post_report_llm_error_returns_message`
5. **빈 제보·너무 긴 제보**(공백만, 5,000자 초과) → 접수 거부(422)와 이유. → Task 7 `test_post_report_rejects_empty_and_too_long`

---

## 파일 구조

```
app/config.py      설정(.env 로드, 모델명, 가격, 경로)
app/llm.py         call_llm + LLMResult + 비용 계산 + 예외
app/schemas.py     Pydantic 모델과 JSON Schema 변환
app/prompts.py     prompts/*.md 조립(기법 플래그 반영)
app/tools.py       더미 데이터 조회 도구 + 도구 정의 + 버전 파서
app/pipeline.py    PipelineConfig + analyze()
app/store.py       제보·대화·로그 JSONL 저장
app/auth.py        개발자 ID 로그인, 세션, 담당자 배정
app/chat.py        멀티턴 챗봇(짧은 기억 + tool 루프)
app/main.py        FastAPI 라우트
prompts/           extract.md, extract_fewshot.md, classify.md, classify_fewshot.md,
                   link.md, score.md, score_rubric.md, score_fewshot.md, chat.md
data/              known_issues.json, releases.json, developers.json, runtime/
static/            index.html(로그인), app.html, app.js, style.css
eval/              dataset_v1.jsonl, grade.py, run_eval.py, results/, runs.csv, runs.xlsx
tests/             conftest.py(FakeClient), test_*.py
CLAUDE.md, README.md, docs/SPEC.md, docs/STATE.md, docs/HISTORY.md
```

---

### Task 1: 프로젝트 뼈대와 설정

**Files:**
- Create: `requirements.txt`, `.env`(없을 때만), `CLAUDE.md`, `docs/SPEC.md`, `docs/STATE.md`, `docs/HISTORY.md`, `pytest.ini`, `app/__init__.py`, `app/config.py`, `tests/__init__.py`, `tests/test_config.py`
- Modify: `.gitignore` (이미 `venv/ .env __pycache__/ data/runtime/` 있음 → `eval/results/` 추가 안 함: 결과는 커밋 대상)

**Interfaces:**
- Produces: `app.config` 상수 `MODEL_DEFAULT = "claude-haiku-5-5"`, `MODEL_COMPARE = "claude-sonnet-5-5"`, `PRICES: dict[str, dict[str, float]]`(키 `input`,`output`,`cache_write`,`cache_read`), `ROOT: Path`, `DATA_DIR: Path`, `RUNTIME_DIR: Path`, `PROMPTS_DIR: Path`; 함수 `get_api_key() -> str`(없거나 placeholder면 `RuntimeError("CLAUDE_API_KEY가 .env에 없습니다")`)

- [ ] **Step 1:** `venv` 생성(`python -m venv venv`), `requirements.txt`에 `fastapi[standard]`, `anthropic`, `python-dotenv`, `pydantic`, `pytest`, `openpyxl` → `venv\Scripts\python.exe -m pip install -r requirements.txt`
- [ ] **Step 2:** `.env`가 없을 때만 `CLAUDE_API_KEY=여기에_API_키를_붙여넣기` 로 생성(BOM 없음). 있으면 손대지 않음
- [ ] **Step 3:** `CLAUDE.md` 작성(영어, 200줄 이하): 실행·테스트 명령, "API calls during development use claude-haiku-5-5 only; the single exception is the Sonnet 5.5 model-comparison eval run", pip 규칙, `.env` 규칙, 그리고 강의 78쪽 상태 관리 규칙(`@docs/SPEC.md`, `@docs/STATE.md` 가져오기, 단계마다 STATE 덮어쓰기 30줄 이내, 작업 끝나면 HISTORY 맨 위 추가, HISTORY는 @로 가져오지 않음, 요청 없어도 스스로 관리). SPEC은 설계 문서 요약+링크, STATE/HISTORY는 초기 내용
- [ ] **Step 4: 실패 테스트** `tests/test_config.py`

```python
def test_get_api_key_rejects_placeholder(monkeypatch):
    monkeypatch.setenv("CLAUDE_API_KEY", "여기에_API_키를_붙여넣기")
    with pytest.raises(RuntimeError):
        config.get_api_key()

def test_prices_cover_both_models():
    assert set(config.PRICES) == {"claude-haiku-5-5", "claude-sonnet-5-5"}
    assert config.PRICES["claude-haiku-5-5"]["input"] == 0.10
```

- [ ] **Step 5:** `venv\Scripts\python.exe -m pytest tests/test_config.py -v` → FAIL(모듈 없음)
- [ ] **Step 6:** `app/config.py` 구현(`load_dotenv(ROOT/".env")`, 환경변수 우선)
- [ ] **Step 7:** 같은 명령 → PASS
- [ ] **Step 8:** 커밋 `chore: scaffold project, config, CLAUDE.md`

### Task 2: 더미 데이터와 조회 도구

**Files:**
- Create: `data/known_issues.json`, `data/releases.json`, `data/developers.json`, `app/tools.py`, `tests/test_tools.py`

**Interfaces:**
- Produces:
  - `parse_version(text: str | None) -> tuple[int, int, int] | None`
  - `version_lt(a: str | None, b: str | None) -> bool | None` (둘 중 하나라도 파싱 불가면 None)
  - `search_known_issues(keywords: list[str], feature_area: str | None = None, android_version: str | None = None, app_version: str | None = None) -> dict` → `{"status": "ok", "issues": [...최대 5]}` 또는 `{"status": "not_found"}`
  - `get_release_info(version: str) -> dict` → `{"status": "ok", "version", "date", "fixed_issues": [...]}` 또는 `{"status": "not_found"}`
  - `ISSUE_TOOL_DEFS: list[dict]` (위 두 도구, `strict: true`, `additionalProperties: false`)
  - `run_tool(name: str, tool_input: dict) -> tuple[str, bool]` → (JSON 문자열, is_error). 모르는 이름·예외는 is_error True

- [ ] **Step 1:** RunBuddy 코드(읽기 전용, `C:\Users\maki2\AndroidStudioProjects\RunBuddy-main`)에서 근거를 찾아 `known_issues.json` 12건 작성. 반드시 포함: Android 7.x 알림 채널 크래시(API 26 미만), Android 14 FGS 위치 타입 누락 크래시, 100ms 위치 요청 배터리 소모, 30m 초과 이동 무시로 거리 과소, 체중 70kg 고정 칼로리 부정확. 나머지는 map/record/card_image/voice/login/ai_chat에서 1건 이상씩. 필드: `id, title, feature_area, symptoms[], affected_android[], affected_app_versions[], status, fixed_in, workaround`. 최소 3건은 `status: "open"`
- [ ] **Step 2:** `releases.json`: `1.0`, `1.0.1`, `1.1.0`, `1.1.1`, `1.2.0`(날짜 포함), `fixed_issues`가 known_issues의 `fixed_in`과 일치. `developers.json`: `dev1`(tracking, voice, login), `dev2`(map, record, card_image), `dev3`(ai_chat, other)
- [ ] **Step 3: 실패 테스트**

```python
@pytest.mark.parametrize("text,expected", [
    ("1.0", (1, 0, 0)), ("v1.0.1", (1, 0, 1)), ("1.0.1 버전", (1, 0, 1)),
    ("최신", None), (None, None), ("", None)])
def test_parse_version_variants(text, expected): ...

def test_version_lt_unknown_is_none(): assert tools.version_lt("최신", "1.0.1") is None
def test_search_finds_android14_crash():
    r = tools.search_known_issues(["크래시", "시작"], feature_area="tracking", android_version="14")
    assert r["status"] == "ok" and any("14" in " ".join(i["affected_android"]) for i in r["issues"])
def test_search_not_found(): assert tools.search_known_issues(["존재하지않는단어xyz"])["status"] == "not_found"
def test_release_not_found(): assert tools.get_release_info("9.9.9")["status"] == "not_found"
def test_run_tool_unknown_name_is_error(): assert tools.run_tool("nope", {})[1] is True
def test_data_consistency():  # 모든 fixed_in이 releases에 있고 그 버전의 fixed_issues에 포함
```

- [ ] **Step 4:** `pytest tests/test_tools.py -v` → FAIL
- [ ] **Step 5:** `app/tools.py` 구현. 검색 점수 = 키워드가 title/symptoms에 포함된 개수 + feature_area 일치 가산 + android_version 일치 가산, 점수 0 제외, 상위 5개
- [ ] **Step 6:** PASS 확인
- [ ] **Step 7:** 커밋 `feat: dummy issue data and lookup tools`

### Task 3: 스키마와 LLM 호출 래퍼

**Files:**
- Create: `app/schemas.py`, `app/llm.py`, `tests/conftest.py`, `tests/test_llm.py`, `tests/test_schemas.py`

**Interfaces:**
- Produces (`app/schemas.py`):
  - `Extraction`: `device_model, android_version, app_version, feature_area, symptom, expected, actual, frequency: str | None`, `repro_steps: list[str]`, `missing_fields: list[str]`
  - `Classification`: `category: Literal[...]`, `labels: list[category]`, `reason: str`
  - `Link`: `linked_issue_id: str | None`, `match_reason: str | None`, `fixed_in: str | None`, `user_should_update: bool | None`
  - `Score`: `reasoning: str`(CoT, 먼저 출력), `completeness: Literal[0,1,2] | None`, `priority: Literal["P1".."P4"]`, `questions_to_reporter: list[str]`
  - `TriageResult`: `extraction, classification, link: Link | None, score, answer_status: Literal["ready","need_info"]` (설계의 `unsupported`는 처리 규칙이 없어 제외 — 계획 작성자 결정)
  - `to_json_schema(model: type[BaseModel]) -> dict` (모든 object에 `additionalProperties: false`, 모든 필드 required, nullable은 `anyOf [..., {"type":"null"}]`)
- Produces (`app/llm.py`):
  - `@dataclass Usage(input_tokens:int, output_tokens:int, cache_read:int, cache_write:int)`
  - `@dataclass LLMResult(content: list, text: str, parsed: dict | None, stop_reason: str, usage: Usage, latency_s: float, cost_usd: float, model: str)`
  - `class LLMError(Exception)`, 하위 `LLMRefusal`, `LLMTruncated`, `LLMUnavailable`(API 연결·429·5xx)
  - `cost_usd(model: str, usage: Usage) -> float`
  - `get_client() -> anthropic.Anthropic` (테스트에서 monkeypatch)
  - `call_llm(*, step: str, system: list[dict], messages: list[dict], schema: dict | None = None, tools: list[dict] | None = None, model: str = MODEL_DEFAULT, effort: str = "low", max_tokens: int = 4096, stop_sequences: list[str] | None = None) -> LLMResult` (`stop_sequences`는 None이면 보내지 않음)
    - `schema`가 있으면 `output_config={"format": {"type":"json_schema","schema": schema}, "effort": effort}`, 없으면 `{"effort": effort}`; `parsed`는 마지막 text 블록 `json.loads`
    - `tools`가 있으면 `tool_choice={"type":"auto"}`
    - SDK 예외는 `AuthenticationError → LLMError("API 키 오류")`, `RateLimitError/APIStatusError(>=500)/APIConnectionError → LLMUnavailable` 순서로 변환
- Consumes: `config.PRICES`, `config.get_api_key`

- [ ] **Step 1:** `tests/conftest.py`에 `FakeClient`(미리 넣어 둔 응답 목록을 순서대로 반환, 받은 kwargs 기록)와 `fake_llm` fixture(`llm.get_client`를 대체) 작성. 응답 객체는 `SimpleNamespace(content=[...], stop_reason=..., usage=SimpleNamespace(input_tokens, output_tokens, cache_read_input_tokens, cache_creation_input_tokens))`
- [ ] **Step 2: 실패 테스트**

```python
def test_cost_haiku():
    u = Usage(1_000_000, 1_000_000, 0, 0)
    assert llm.cost_usd("claude-haiku-5-5", u) == pytest.approx(0.60)
def test_call_parses_json(fake_llm): ...           # text '{"a":1}' → parsed == {"a":1}, cost>0
def test_call_sends_schema_and_effort(fake_llm): ... # kwargs["output_config"]["format"]["type"] == "json_schema"
def test_call_uses_auto_tool_choice(fake_llm): ...   # tools 주면 tool_choice == {"type":"auto"}
def test_call_raises_on_refusal(fake_llm): ...       # stop_reason "refusal" → LLMRefusal
def test_call_raises_on_max_tokens(fake_llm): ...    # → LLMTruncated
def test_schema_all_required_no_extra():             # to_json_schema(Extraction): required == 모든 필드, additionalProperties False
```

- [ ] **Step 3:** `pytest tests/test_llm.py tests/test_schemas.py -v` → FAIL
- [ ] **Step 4:** 구현
- [ ] **Step 5:** PASS 확인
- [ ] **Step 6: 실호출 스모크(Haiku, 1회)** `venv\Scripts\python.exe -c "from app.llm import call_llm; from app.schemas import Classification, to_json_schema; r=call_llm(step='smoke', system=[{'type':'text','text':'분류만 해.'}], messages=[{'role':'user','content':'달리기 시작하면 앱이 꺼져요'}], schema=to_json_schema(Classification)); print(r.parsed, r.usage, round(r.cost_usd,6))"` → `category`가 들어 있는 dict 출력. 400이 나면 스키마 제약(지원 안 되는 키워드)을 고치고 재시도
- [ ] **Step 7:** 커밋 `feat: schemas and Claude call wrapper with cost logging`

### Task 4: 프롬프트와 분석 파이프라인

**Files:**
- Create: `prompts/extract.md`, `prompts/extract_fewshot.md`, `prompts/classify.md`, `prompts/classify_fewshot.md`, `prompts/link.md`, `prompts/score.md`, `prompts/score_rubric.md`, `prompts/score_fewshot.md`, `app/prompts.py`, `app/pipeline.py`, `tests/test_prompts.py`, `tests/test_pipeline.py`

**Interfaces:**
- Consumes: `call_llm`, `LLMResult`, 스키마들, `ISSUE_TOOL_DEFS`, `run_tool`, `version_lt`
- Produces:
  - `@dataclass(frozen=True) PipelineConfig(model: str = MODEL_DEFAULT, few_shot: bool = True, rubric: bool = True, context_select: bool = True, effort: str = "low")`; `BASELINE = PipelineConfig(few_shot=False, rubric=False, context_select=False)`
  - `build_system(step: str, cfg: PipelineConfig) -> list[dict]` (in `app/prompts.py`) → 고정 블록들. 마지막 고정 블록에 `cache_control: {"type":"ephemeral"}`. 순서: 공통 규칙(Task/Context/Constraints/Output format/Success criteria) → (few_shot면) 예시 → (rubric면, score만) Rubric
  - `@dataclass StepLog(step: str, model: str, latency_s: float, cost_usd: float, usage: Usage)`
  - `analyze(report_text: str, cfg: PipelineConfig = PipelineConfig(), prior: TriageResult | None = None, added_info: str | None = None) -> tuple[TriageResult, list[StepLog]]`
  - `LINK_MAX_TOOL_ROUNDS = 4`

**프롬프트 내용 규칙(빌더가 작성, 강의 21쪽 Markdown 템플릿):**
- extract: 원문에 없는 값은 반드시 null, 추측 금지. `missing_fields`에는 bug 판단에 필요한데 없는 것(app_version, android_version, device_model, repro_steps)
- classify: 버그 vs 문의 vs 개선 요청 정의 + 복합이면 `labels` 여러 개, 주 라벨은 `category`. few-shot 3개 이상: "GPS 기록 끊김"(bug), "기록 내보내기 되나요?"(question), "체중 설정 넣어주세요"(feature_request), "카드 저장이 안 되는데 공유 기능도 있으면 좋겠어요"(bug+feature_request)
- link: 도구로 조회한 결과에 있는 ID만 연결 가능, 없으면 null. bug가 아니면 이 단계는 호출하지 않음
- score: `reasoning`을 먼저(영향 범위·빈도·우회 가능 여부·데이터 손실 여부) 쓰고 점수. Rubric 파일: 완성도 0/1/2(설계 7절 문구 그대로), 우선순위 P1(크래시·데이터 손실·다수 사용자 영향) / P2(핵심 기능 오동작, 우회 어려움) / P3(우회 가능 또는 일부 사용자) / P4(표시·문구 등 사소)
- `context_select=False`(Baseline)면 각 단계에 원문 전체 + 앞 단계 결과 전체를 보냄. `True`면 classify는 원문+추출, link는 추출 결과만, score는 추출+분류+연결만 보냄
- 원문·조회 결과는 system이 아니라 user 메시지(캐시 뒤쪽)에 둔다

**검증:** 각 단계의 `parsed`는 해당 Pydantic 모델의 `model_validate`로 다시 검증하고, 실패하면 `LLMError("응답 형식 오류")`.

**analyze 흐름:** extract → classify → (category == bug 또는 labels에 bug) 이면 link(tool 루프, 최대 4라운드, 마지막 응답은 Link 스키마) → score. bug가 아니면 `link=None`, `completeness=None`. `answer_status`: 필수 필드(app_version, android_version, repro_steps) 중 2개 이상 없으면 `need_info`, 그 외 `ready`. `user_should_update`는 모델이 아니라 코드가 `version_lt(extraction.app_version, link.fixed_in)`으로 계산. 재분석(`prior`, `added_info`)이면 user 메시지를 "확정 필드(JSON) + 새 정보"로 구성하고 원문 전체는 보내지 않음

- [ ] **Step 1: 실패 테스트** (`fake_llm`에 단계별 응답 주입)

```python
def test_build_system_order_and_cache_marker():
    blocks = prompts.build_system("score", PipelineConfig())
    assert "Rubric" in blocks[-1]["text"] and blocks[-1]["cache_control"] == {"type": "ephemeral"}
def test_build_system_baseline_has_no_examples():
    assert all("Example" not in b["text"] for b in prompts.build_system("classify", BASELINE))
def test_analyze_question_skips_link(fake_llm): ...        # link is None, completeness is None, 3번 호출
def test_analyze_bug_runs_tool_loop(fake_llm): ...         # tool_use → run_tool → tool_result 블록 전달 확인, linked_issue_id 반영
def test_user_should_update_computed_by_code(fake_llm): ... # app_version "1.0", fixed_in "1.0.1" → True
def test_extract_vague_report_keeps_nulls(fake_llm): ...   # 전부 null → answer_status == "need_info"
def test_context_select_link_gets_extraction_only(fake_llm): ... # link 요청 user 메시지에 원문 문자열이 없음
def test_reanalyze_sends_confirmed_fields_not_original(fake_llm): ...
def test_tool_loop_stops_after_max_rounds(fake_llm): ...   # 계속 tool_use면 4라운드 후 LLMError
```

- [ ] **Step 2:** FAIL 확인 → **Step 3:** 프롬프트 파일과 구현 → **Step 4:** PASS 확인
- [ ] **Step 5: 실호출 확인(Haiku)** 제보 3개로 `analyze` 실행(Android 14 크래시 / 질문 / 정보 거의 없는 제보) → 결과 JSON과 단계별 비용 출력. 2번째 실행에서 `cache_read > 0`인지 확인하고, 0이면 고정 블록 토큰 수와 함께 `docs/STATE.md`에 기록(설계 12절: 억지로 늘리지 않음)
- [ ] **Step 6:** 커밋 `feat: prompt templates and 4-step triage pipeline`

### Task 5: 저장소, 로그인, 담당자 배정

**Files:**
- Create: `app/store.py`, `app/auth.py`, `tests/test_store.py`, `tests/test_auth.py`

**Interfaces:**
- Produces (`app/store.py`): `class Store(base_dir: Path)`
  - `create_report(dev_id: str, text: str, result: TriageResult, logs: list[StepLog]) -> str` (다음 `R-%04d`, 개발자 상관없이 전역 증가)
  - `get_report(dev_id: str, request_id: str) -> dict | None` (담당자가 아니면 None)
  - `list_reports(dev_id: str, priority: str | None = None, category: str | None = None) -> list[dict]` (P1→P4, 같은 우선순위는 최신 먼저)
  - `update_report(dev_id: str, request_id: str, result: TriageResult, logs: list[StepLog], added_info: str) -> None`
  - `append_chat(dev_id: str, role: str, content: str) -> None`, `get_chat(dev_id: str) -> list[dict]`
  - 저장 형식: `runtime/<dev_id>/reports.jsonl`(최신 상태를 매번 다시 씀), `runtime/<dev_id>/chat.jsonl`, `runtime/logs.jsonl`(단계별 로그 추가, 한 줄마다 `request_id`·`dev_id`·`step`·`model`·토큰·`latency_s`·`cost_usd`·`cache_read`·시각을 넣어 결과와 로그를 연결)
- Produces (`app/auth.py`): `load_developers() -> dict[str, list[str]]`, `assign_developer(feature_area: str | None) -> str`(매칭 없으면 `dev3`), `login(dev_id: str) -> str`(토큰, 모르는 ID면 `ValueError`), `current_dev(request: Request) -> str`(쿠키 `session`의 토큰 확인, 없으면 401) — 토큰은 서버 메모리 dict

- [ ] **Step 1: 실패 테스트**

```python
def test_ids_increment(tmp_path): ...                # R-0001, R-0002
def test_get_report_other_dev_404(tmp_path):
    rid = store.create_report("dev1", "...", result, [])
    assert store.get_report("dev2", rid) is None
def test_list_sorted_by_priority(tmp_path): ...
def test_assign_developer_by_area(): assert auth.assign_developer("map") == "dev2"
def test_assign_unknown_area_goes_dev3(): assert auth.assign_developer(None) == "dev3"
def test_login_unknown_id_raises(): ...
```

- [ ] **Step 2:** FAIL → **Step 3:** 구현 → **Step 4:** PASS
- [ ] **Step 5:** 커밋 `feat: per-developer store and ID login`

### Task 6: 멀티턴 챗봇

**Files:**
- Create: `prompts/chat.md`, `app/chat.py`, `tests/test_chat.py`

**Interfaces:**
- Consumes: `call_llm`, `ISSUE_TOOL_DEFS`, `run_tool`, `Store`, `analyze`, `PipelineConfig`
- Produces:
  - `KEEP_TURNS = 6`
  - `CHAT_TOOL_DEFS: list[dict]` = 이슈 도구 2개 + `list_my_reports(priority?, category?)`, `get_report(request_id)`, `reanalyze_report(request_id, added_info)` (모두 `strict: true`)
  - `run_chat_tool(dev_id: str, store: Store, name: str, tool_input: dict) -> tuple[str, bool]` (제보 도구는 항상 `dev_id`로 제한 → 남의 제보는 `{"status":"not_found"}`)
  - `build_messages(history: list[dict], state_summary: str, user_message: str, keep_turns: int = KEEP_TURNS) -> list[dict]` → 오래된 턴은 빼고, 첫 user 메시지 앞부분에 `[상태 요약]` 블록, 마지막에 이번 질문
  - `summarize_state(dev_id: str, store: Store, history: list[dict]) -> str` (코드로 만드는 요약: 최근 언급된 R-ID, 내 P1/P2 개수, 미해결 질문. LLM 호출 없음)
  - `@dataclass ChatReply(text: str, tool_calls: list[str], cost_usd: float, latency_s: float, cache_read: int)`
  - `chat_turn(dev_id: str, message: str, store: Store, model: str = MODEL_DEFAULT) -> ChatReply` (tool 루프 최대 5라운드, system은 고정 블록 + 도구 정의로 캐시)

- [ ] **Step 1: 실패 테스트**

```python
def test_build_messages_keeps_last_6_turns(): ...      # 10턴 이력 → 원문 6턴 + 상태 요약
def test_state_summary_mentions_recent_report_ids(tmp_path): ...
def test_chat_tool_cannot_read_other_dev_report(tmp_path):
    out, is_err = chat.run_chat_tool("dev2", store, "get_report", {"request_id": rid_of_dev1})
    assert json.loads(out)["status"] == "not_found"
def test_chat_turn_runs_reanalyze_tool(fake_llm, tmp_path): ...  # tool_use reanalyze_report → store 갱신
def test_chat_turn_saves_history(fake_llm, tmp_path): ...
```

- [ ] **Step 2:** FAIL → **Step 3:** 구현 → **Step 4:** PASS
- [ ] **Step 5: 실호출 시나리오(Haiku)** 3턴: "내 P1 제보 보여줘" → "첫 번째랑 비슷한 이슈 있어?" → "그 제보자 앱 버전은 1.0이래" → 도구 호출 이름과 답, 2·3턴 `cache_read` 출력
- [ ] **Step 6:** 커밋 `feat: multi-turn developer chatbot with short-term memory`

### Task 7: FastAPI 라우트와 화면

**Files:**
- Create: `app/main.py`, `static/index.html`, `static/app.html`, `static/app.js`, `static/style.css`, `tests/test_api.py`

**Interfaces:**
- Consumes: `analyze`, `Store`, `auth.*`, `chat_turn`, `LLMError`
- Produces: 설계 9절 API 그대로. 요청 바디: `POST /api/login {"dev_id"}`; `POST /api/reports {"text"}`(1~5,000자, 공백만 거부); `POST /api/reports/{id}/reanalyze {"added_info"}`; `POST /api/chat {"message"}`. 응답의 제보 객체: `{request_id, dev_id, text, result, logs_summary: {latency_s, cost_usd, cache_read}, created_at, updated_at}`. `LLMRefusal/LLMTruncated` → 422 `{"detail": "모델이 이 제보를 처리하지 못했습니다..."}`, `LLMUnavailable` → 502. 접수된 제보는 `assign_developer(extraction.feature_area)` 담당자에게 저장되고, 응답에 `assigned_to` 포함
- 앱 상태: `app.state.store = Store(RUNTIME_DIR)`; 테스트는 `tmp_path` Store와 목 `analyze`로 교체

**화면:** `index.html` 로그인(ID 입력) → `app.html` 왼쪽: 제보 입력, 내 제보 목록(우선순위 배지), 선택한 제보 상세(설계 9절 스케치 항목, "제보 원문"과 "조회한 사실" 구분, 부족한 정보 입력 + 다시 분석, 처리 시간·비용·캐시 토큰); 오른쪽: 챗봇(대화, 사용한 도구 이름 표시). 프레임워크 없이 fetch

- [ ] **Step 1: 실패 테스트** (FastAPI `TestClient`)

```python
def test_login_sets_cookie_and_unknown_401(): ...
def test_reports_require_login(): ...                         # 쿠키 없으면 401
def test_post_report_rejects_empty_and_too_long(client): ...  # "   " → 422, "가"*5001 → 422
def test_post_report_assigns_developer(client, monkeypatch): ...
def test_post_report_llm_error_returns_message(client, monkeypatch): ...  # LLMRefusal → 422 + 한국어 detail
def test_get_report_of_other_dev_is_404(client): ...
def test_chat_endpoint_returns_reply(client, monkeypatch): ...
```

- [ ] **Step 2:** FAIL → **Step 3:** 구현 → **Step 4:** PASS, 전체 `pytest -q` PASS
- [ ] **Step 5: 수동 확인** `venv\Scripts\python.exe -m uvicorn app.main:app --port 8000` 실행 후 `Invoke-RestMethod`로 로그인 → 제보 접수 → 조회 → 챗 1턴, 그리고 사용자에게 브라우저에서 `http://127.0.0.1:8000` 확인 요청(내장 브라우저는 로컬 서버를 열 수 없음)
- [ ] **Step 6:** 커밋 `feat: FastAPI service with login, triage view and chatbot`

### Task 8: 평가셋 100건

**Files:**
- Create: `eval/dataset_v1.jsonl`, `eval/check_dataset.py`, `tests/test_dataset.py`

**Interfaces:**
- Produces: 한 줄 형식 `{"id": "E-001", "text": "...", "hard": bool, "tags": [...], "expected": {"category", "labels", "extraction": {Extraction 필드}, "completeness", "priority", "linked_issue_id"}}`

- [ ] **Step 1: 실패 테스트** — `tests/test_dataset.py`: 100줄, id 중복 없음, 모든 expected가 스키마 열거값을 지킴, `hard` ≥ 10, category별 최소 20건, `linked_issue_id`가 있으면 known_issues에 존재, 정보 누락 사례(`missing` 태그) ≥ 15, 복합 라벨 ≥ 8
- [ ] **Step 2:** FAIL → **Step 3:** Claude Code가 직접 작성(사람이 쓴 듯한 한국어 제보, 오타·구어체 포함, 기기·버전 표기 다양화, Review Focus 1·3 사례 포함). 어려운 사례: 버그/문의 경계, 버그/개선 경계, 크래시인데 정보 없음, 알려진 이슈와 비슷하지만 다른 버전, 이미 수정된 버전 사용자
- [ ] **Step 4:** PASS → `eval/check_dataset.py`로 분포 표 출력
- [ ] **Step 5: 사용자 검토** 어려운 사례 10건을 표(아티팩트 또는 마크다운)로 보여주고 정답 수정 요청을 받아 반영. 승인 후 `dataset_v1` 고정(이후 수정 금지, 바꾸려면 v2)
- [ ] **Step 6:** 커밋 `data: eval dataset v1 (100 cases)`

### Task 9: 채점과 평가 실행기

**Files:**
- Create: `eval/__init__.py`, `eval/grade.py`, `eval/run_eval.py`, `tests/test_grade.py`, `tests/test_run_eval.py`

**Interfaces:**
- Produces (`eval/grade.py`, 순수 함수):
  - `classification_metrics(expected: list[str], predicted: list[str]) -> dict` → `{"accuracy", "macro_f1", "confusion": dict[str, dict[str, int]]}` (라벨 3개 고정 순서)
  - `extraction_metrics(expected: list[dict], predicted: list[dict]) -> dict` → 필드별 `accuracy`, `hallucination_rate`(정답 null인데 값 생성), `miss_rate`(정답 있는데 null). 문자열 비교는 공백·대소문자 정규화, 버전은 `parse_version`으로 비교
  - `completeness_mae(expected, predicted) -> float | None` (둘 다 숫자인 쌍만)
  - `priority_metrics(expected, predicted) -> dict` → `{"exact", "within_1"}`
  - `link_accuracy(expected, predicted) -> float` (None끼리 일치도 정답)
- Produces (`eval/run_eval.py`): CLI `--run-id`, `--model`(기본 haiku), `--baseline`(BASELINE 설정) 또는 `--no-few-shot/--no-rubric/--no-context-select`, `--effort`, `--change "설명"`, `--limit N`, `--only-hard`
  - 동작: 데이터셋 각 건 `analyze(text, cfg)` → 건별 `eval/results/<run_id>.csv`(utf-8-sig; 입력, 정답, 예측, 정오, 지연, 비용) → `eval/results/<run_id>_confusion.csv` → `eval/runs.csv`에 한 줄 추가(날짜, Run ID, 모델, 설정, 분류 acc/F1, 추출 평균 정확도·환각률, MAE, P exact/±1, 링크 정확도, 평균 응답시간, 총비용, 캐시 적중 토큰 합, 변경사항) → `eval/runs.xlsx` 재생성(시트: runs, 각 run 요약)
  - 실패 건(LLMError)은 건너뛰지 않고 "오류"로 기록하고 정답 처리하지 않음

- [ ] **Step 1: 실패 테스트**

```python
def test_classification_metrics_known_values():
    m = grade.classification_metrics(["bug","bug","question"], ["bug","question","question"])
    assert m["accuracy"] == pytest.approx(2/3)
    assert m["confusion"]["bug"]["question"] == 1
def test_extraction_counts_hallucination(): ...   # 정답 None, 예측 "1.0" → hallucination_rate 1.0
def test_extraction_version_normalized(): ...     # "v1.0.1" vs "1.0.1" 일치
def test_link_accuracy_none_matches_none(): ...
def test_run_eval_appends_row(tmp_path, monkeypatch): ...  # analyze를 목으로 → runs.csv 한 줄, 변경사항 컬럼 포함
def test_run_eval_records_errors(tmp_path, monkeypatch): ...
```

- [ ] **Step 2:** FAIL → **Step 3:** 구현 → **Step 4:** PASS
- [ ] **Step 5:** `--limit 3` 실호출로 동작 확인(Haiku), 결과 파일 확인 후 삭제하지 말고 `Run-00-smoke`로 남김
- [ ] **Step 6:** 커밋 `feat: grading functions and eval runner`

### Task 10: Baseline과 한 변수씩 개선 Run

**Files:**
- Modify: `prompts/*.md`(Run-06 이후 개선에서만), `eval/runs.csv`, `eval/runs.xlsx`, `eval/results/*`, `docs/STATE.md`, `docs/HISTORY.md`

- [ ] **Step 1:** 실행 전 예상 비용을 계산해 사용자에게 알리고 진행(100건 × 4단계, Haiku 기준 수 센트, Sonnet Run은 수십 센트~1달러 내외)
- [ ] **Step 2:** `Run-01` `--baseline --change "기준선: 지시문만, 전체 원문 전달"`
- [ ] **Step 3:** `Run-02` Baseline + few_shot `--change "Few-shot 예시 추가"`
- [ ] **Step 4:** `Run-03` + rubric `--change "Rubric 추가"`
- [ ] **Step 5:** `Run-04` + context_select `--change "Context 선별"` (= 기본 설정)
- [ ] **Step 6:** `Run-05` 기본 설정 + `--model claude-sonnet-5-5 --change "모델 비교: Sonnet"`
- [ ] **Step 7:** 각 Run 후 지표를 표로 사용자에게 보여주고, 틀린 사례 정성 분석(실패 유형 분류)을 아티팩트로 만들어 다음에 바꿀 변수 1개 제안
- [ ] **Step 8:** `Run-06+` 실패 유형 기반 개선 1개씩(사용자와 상의), 각각 `--change`로 기록. 개선이 아니면 되돌리고 그 사실도 기록
- [ ] **Step 9:** 최종 설정 결정(품질·응답시간·비용 기준)과 근거를 `docs/HISTORY.md`에 기록, 커밋 `eval: baseline and one-variable experiments`

### Task 11: 분석 아티팩트와 README

**Files:**
- Create: `README.md`, `docs/artifacts/*.html`(아티팩트 원본)

- [ ] **Step 1:** README: 실행법(`venv\Scripts\activate`, `uvicorn app.main:app`), 화면 사용법, **기법 → 구현 위치 대응표**(설계 6절을 실제 파일:함수로), 평가 요약 표(Run별), 캐시 적중 결과, 알려진 한계
- [ ] **Step 2:** 아티팩트 4종(설계 10절): Chaining 구조와 단계별 프롬프트, Function calling 흐름, 서비스 워크플로우·컨텍스트 엔지니어링·프롬프트 배치, 평가 결과(어려운 사례 10건 + Run 비교 + 틀린 사례). Artifact 도구로 게시하고 링크를 README에 기록
- [ ] **Step 3:** 최종 확인: `pytest -q` 전체 PASS, 서버 기동, 화면 시나리오 1회, `pip freeze > requirements.lock.txt`
- [ ] **Step 4:** 커밋 `docs: README with technique map and analysis artifacts`
