import json
from types import SimpleNamespace as NS

import pytest

from app.llm import LLMError
from app.pipeline import BASELINE, LINK_MAX_TOOL_ROUNDS, PipelineConfig, analyze
from app.schemas import TriageResult
from tests.conftest import make_response

REPORT = "갤럭시 S23, 안드로이드 14에서 러닝 시작 누르면 앱이 바로 꺼져요. 로그인하고 달리기 시작 버튼 누르면 매번 그래요."


def extraction(**over):
    base = {
        "device_model": "Galaxy S23", "android_version": "14", "app_version": None,
        "feature_area": "tracking", "symptom": "러닝 시작 시 앱 종료", "expected": "러닝 기록 시작",
        "actual": "앱 종료", "frequency": "매번",
        "repro_steps": ["로그인", "달리기 시작 버튼 터치"], "missing_fields": ["app_version"],
    }
    base.update(over)
    return base


def classification(category="bug", labels=None):
    return {"category": category, "labels": labels or [category], "reason": "근거"}


def link(issue_id=None, fixed_in=None, should_update=None):
    return {"linked_issue_id": issue_id, "match_reason": "증상 일치" if issue_id else None,
            "fixed_in": fixed_in, "user_should_update": should_update}


def score(completeness=1, priority="P1"):
    return {"reasoning": "크래시이며 다수 사용자 영향", "completeness": completeness, "priority": priority,
            "questions_to_reporter": ["앱 버전을 알려주세요"]}


def jr(obj):
    return make_response(json.dumps(obj, ensure_ascii=False))


def tool_use(name, tool_input, tid="tu_1"):
    return make_response(stop_reason="tool_use", content=[
        NS(type="thinking", thinking="", signature="sig"),
        NS(type="tool_use", id=tid, name=name, input=tool_input),
    ])


SEARCH_CRASH = {"keywords": ["크래시"], "feature_area": "tracking", "android_version": "14", "app_version": None}


def user_texts(call):
    out = []
    for m in call["messages"]:
        if m["role"] != "user":
            continue
        if isinstance(m["content"], str):
            out.append(m["content"])
        else:
            out.extend(b.get("text", "") or b.get("content", "") for b in m["content"])
    return "\n".join(out)


def test_analyze_question_skips_link(fake_llm):
    fake_llm.queue(
        jr(extraction(device_model=None, android_version=None, repro_steps=[], missing_fields=[])),
        jr(classification("question")),
        jr(score(completeness=2, priority="P4")),
    )
    result, logs = analyze("기록 내보내기 되나요?")
    assert isinstance(result, TriageResult)
    assert result.link is None
    assert result.score.completeness is None  # forced by code for non-bugs
    assert len(fake_llm.calls) == 3
    assert [l.step for l in logs] == ["extract", "classify", "score"]
    assert all("tools" not in c for c in fake_llm.calls)


def test_analyze_bug_runs_tool_loop(fake_llm):
    fake_llm.queue(
        jr(extraction()), jr(classification()),
        tool_use("search_known_issues", SEARCH_CRASH),
        jr(link("ISSUE-02", "1.2.0")),
        jr(score()),
    )
    result, logs = analyze(REPORT)
    link_calls = fake_llm.calls[2:4]
    assert all(c["tools"] for c in link_calls)
    assert all(c["output_config"]["format"]["type"] == "json_schema" for c in link_calls)
    msgs = link_calls[1]["messages"]
    # assistant turn replayed unchanged (thinking block included)
    assert msgs[1]["role"] == "assistant"
    assert [b.type for b in msgs[1]["content"]] == ["thinking", "tool_use"]
    # all tool results in ONE user message
    results = msgs[2]["content"]
    assert msgs[2]["role"] == "user" and len(results) == 1
    assert results[0]["type"] == "tool_result" and results[0]["tool_use_id"] == "tu_1"
    assert results[0]["is_error"] is False and "ISSUE-02" in results[0]["content"]
    assert result.link.linked_issue_id == "ISSUE-02"
    assert result.link.fixed_in == "1.2.0"
    assert [l.step for l in logs] == ["extract", "classify", "link", "link", "score"]


def test_tool_loop_runs_parallel_calls_and_reports_errors(fake_llm):
    fake_llm.queue(
        jr(extraction()), jr(classification()),
        make_response(stop_reason="tool_use", content=[
            NS(type="tool_use", id="a", name="search_known_issues", input=SEARCH_CRASH),
            NS(type="tool_use", id="b", name="no_such_tool", input={}),
        ]),
        jr(link("ISSUE-02", "1.2.0")), jr(score()),
    )
    analyze(REPORT)
    results = fake_llm.calls[3]["messages"][2]["content"]
    assert [r["tool_use_id"] for r in results] == ["a", "b"]
    assert [r["is_error"] for r in results] == [False, True]


def test_user_should_update_computed_by_code(fake_llm):
    fake_llm.queue(
        jr(extraction(app_version="1.0", feature_area="login", missing_fields=[])),
        jr(classification()),
        tool_use("search_known_issues", {"keywords": ["로그인"], "feature_area": "login",
                                         "android_version": None, "app_version": "1.0"}),
        jr(link("ISSUE-11", "1.0.1", should_update=False)),  # model says False; code must override
        jr(score()),
    )
    result, _ = analyze("1.0 버전에서 로그인이 안 돼요")
    assert result.link.fixed_in == "1.0.1"
    assert result.link.user_should_update is True


def test_link_rejects_issue_id_not_returned_by_tools(fake_llm):
    fake_llm.queue(
        jr(extraction()), jr(classification()),
        jr(link("ISSUE-99", "9.9.9", should_update=True)),  # no tool call at all
        jr(score()),
    )
    result, _ = analyze(REPORT)
    assert result.link.linked_issue_id is None
    assert result.link.fixed_in is None
    assert result.link.user_should_update is None


def test_extract_vague_report_keeps_nulls(fake_llm):
    nulls = {k: None for k in ["device_model", "android_version", "app_version", "feature_area",
                               "symptom", "expected", "actual", "frequency"]}
    fake_llm.queue(
        jr({**nulls, "repro_steps": [], "missing_fields": []}),
        jr(classification()),
        jr(link()),
        jr(score(completeness=0, priority="P3")),
    )
    result, _ = analyze("앱이 이상해요")
    ex = result.extraction
    assert ex.app_version is None and ex.android_version is None and ex.device_model is None
    assert ex.repro_steps == []
    assert set(ex.missing_fields) >= {"app_version", "android_version", "device_model", "repro_steps"}
    assert result.answer_status == "need_info"


def test_answer_status_ready_when_at_most_one_required_missing(fake_llm):
    fake_llm.queue(jr(extraction()), jr(classification()), jr(link()), jr(score()))
    result, _ = analyze(REPORT)  # only app_version missing
    assert result.answer_status == "ready"
    assert result.extraction.missing_fields == ["app_version"]


def test_multi_label_bug_runs_link(fake_llm):
    fake_llm.queue(
        jr(extraction(feature_area="card_image")),
        jr(classification("feature_request", ["feature_request", "bug"])),
        jr(link()), jr(score()),
    )
    result, logs = analyze("카드 저장이 안 되는데 공유 기능도 있으면 좋겠어요")
    assert "link" in [l.step for l in logs]
    assert result.link is not None


def test_context_select_link_gets_extraction_only(fake_llm):
    fake_llm.queue(jr(extraction()), jr(classification()), jr(link()), jr(score()))
    analyze(REPORT, PipelineConfig())
    link_text = user_texts(fake_llm.calls[2])
    assert REPORT not in link_text
    assert "Galaxy S23" in link_text
    score_text = user_texts(fake_llm.calls[3])
    assert REPORT not in score_text
    classify_text = user_texts(fake_llm.calls[1])
    assert REPORT in classify_text and "Galaxy S23" in classify_text


def test_baseline_sends_full_report_to_every_step(fake_llm):
    fake_llm.queue(jr(extraction()), jr(classification()), jr(link()), jr(score()))
    analyze(REPORT, BASELINE)
    for call in fake_llm.calls:
        assert REPORT in user_texts(call)
    # score sees every previous result
    assert '"category"' in user_texts(fake_llm.calls[3]) and '"linked_issue_id"' in user_texts(fake_llm.calls[3])


def test_report_text_never_in_system(fake_llm):
    fake_llm.queue(jr(extraction()), jr(classification()), jr(link()), jr(score()))
    analyze(REPORT, BASELINE)
    for call in fake_llm.calls:
        assert all(REPORT not in b["text"] for b in call["system"])


def test_reanalyze_sends_confirmed_fields_not_original(fake_llm):
    fake_llm.queue(jr(extraction()), jr(classification()), jr(link()), jr(score()))
    prior, _ = analyze(REPORT)
    fake_llm.calls.clear()
    fake_llm.queue(
        jr(extraction(app_version="1.1.0", missing_fields=[])), jr(classification()),
        tool_use("search_known_issues", SEARCH_CRASH),
        jr(link("ISSUE-02", "1.2.0")), jr(score(completeness=2)),
    )
    result, _ = analyze(REPORT, prior=prior, added_info="앱 버전은 1.1.0입니다")
    for call in fake_llm.calls:
        assert REPORT not in user_texts(call)
    first = user_texts(fake_llm.calls[0])
    assert "앱 버전은 1.1.0입니다" in first and "Galaxy S23" in first and "확정" in first
    assert result.extraction.app_version == "1.1.0"
    assert result.link.user_should_update is True


def test_tool_loop_stops_after_max_rounds(fake_llm):
    fake_llm.queue(jr(extraction()), jr(classification()),
                   *[tool_use("search_known_issues", SEARCH_CRASH, tid=f"t{i}")
                     for i in range(LINK_MAX_TOOL_ROUNDS + 1)])
    with pytest.raises(LLMError):
        analyze(REPORT)
    assert len(fake_llm.calls) == 2 + LINK_MAX_TOOL_ROUNDS + 1


def test_invalid_step_output_raises_format_error(fake_llm):
    fake_llm.queue(jr({"device_model": "x"}))  # missing required fields
    with pytest.raises(LLMError, match="응답 형식 오류"):
        analyze(REPORT)


def test_non_json_output_raises_format_error(fake_llm):
    fake_llm.queue(make_response("not json"))
    with pytest.raises(LLMError, match="응답 형식 오류"):
        analyze(REPORT)


def test_step_logs_carry_cost_and_usage(fake_llm):
    fake_llm.queue(jr(extraction()), jr(classification("question")), jr(score()))
    _, logs = analyze("기록 내보내기 되나요?")
    assert all(l.model == "claude-haiku-5-5" and l.cost_usd > 0 and l.usage.input_tokens == 100 for l in logs)


def test_config_effort_and_model_passed_through(fake_llm):
    fake_llm.queue(jr(extraction()), jr(classification("question")), jr(score()))
    analyze("질문", PipelineConfig(effort="medium"))
    assert all(c["output_config"]["effort"] == "medium" for c in fake_llm.calls)
    assert all(c["model"] == "claude-haiku-5-5" for c in fake_llm.calls)


def test_non_bug_has_no_missing_fields(fake_llm):
    fake_llm.queue(
        jr(extraction(device_model=None, android_version=None, repro_steps=[],
                      missing_fields=["app_version", "android_version", "device_model", "repro_steps"])),
        jr(classification("question")), jr(score(completeness=None, priority="P4")),
    )
    result, _ = analyze("기록 내보내기 되나요?")
    assert result.extraction.missing_fields == []
    assert '"missing_fields": []' in user_texts(fake_llm.calls[2])  # score sees the cleared list
    assert result.answer_status == "ready"


# ---------- iOS reports ----------

def test_ios_report_needs_ios_version_not_android(fake_llm):
    fake_llm.queue(
        jr(extraction(device_model="아이폰 15", platform="ios", android_version=None, ios_version=None,
                      app_version="1.2.0", missing_fields=[])),
        jr(classification()), jr(link()), jr(score()))
    result, _ = analyze("아이폰 15, 앱 1.2.0. 러닝 시작하면 꺼져요")
    assert result.extraction.missing_fields == ["ios_version"]  # not android_version
    assert result.answer_status == "ready"  # only the OS version is missing


def test_ios_report_with_ios_version_is_complete(fake_llm):
    fake_llm.queue(
        jr(extraction(device_model="아이폰 15", platform="ios", android_version=None, ios_version="17.5",
                      app_version="1.2.0", missing_fields=[])),
        jr(classification()), jr(link()), jr(score()))
    result, _ = analyze("아이폰 15 / iOS 17.5 / 1.2.0. 러닝 시작 누르면 꺼져요")
    assert result.extraction.missing_fields == []


def test_ios_report_is_never_linked_to_an_android_only_issue(fake_llm):
    fake_llm.queue(
        jr(extraction(device_model="아이폰 15", platform="ios", android_version=None, ios_version="17.5",
                      app_version="1.1.1", missing_fields=[])),
        jr(classification()),
        tool_use("search_known_issues", {**SEARCH_CRASH, "android_version": None, "app_version": "1.1.1"}),
        jr(link("ISSUE-02", "1.2.0")),
        jr(score()))
    result, _ = analyze("아이폰 15 / iOS 17.5 / 1.1.1. 러닝 시작 누르면 꺼져요")
    assert result.link.linked_issue_id is None and "안드로이드 전용" in result.link.match_reason


def test_old_saved_result_without_platform_still_loads():
    from app.schemas import TriageResult
    from tests.test_store import make_result
    raw = make_result().model_dump(mode="json")
    del raw["extraction"]["platform"], raw["extraction"]["ios_version"]
    assert TriageResult.model_validate(raw).extraction.platform is None
