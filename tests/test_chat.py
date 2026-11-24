import json
from types import SimpleNamespace as NS

from app import chat
from app.store import Store
from tests.conftest import make_response
from tests.test_pipeline import classification, extraction, jr, link, score
from tests.test_store import make_result


def hist(n):
    return [{"role": "user" if i % 2 == 0 else "assistant", "content": f"m{i}"} for i in range(n)]


def tool_use(name, tool_input, tid="tu_1"):
    return make_response(stop_reason="tool_use", content=[
        NS(type="tool_use", id=tid, name=name, input=tool_input)])


def test_build_messages_keeps_last_6_turns():
    msgs = chat.build_messages(hist(20), "요약내용", "이번 질문")
    assert len(msgs) == 13  # 6 pairs (12 messages) + the current question
    assert msgs[0]["role"] == "user" and msgs[0]["content"].startswith("[상태 요약]")
    assert "요약내용" in msgs[0]["content"] and "m8" in msgs[0]["content"]
    assert "m7" not in json.dumps(msgs, ensure_ascii=False)
    assert msgs[-1] == {"role": "user", "content": "이번 질문"}
    assert [m["role"] for m in msgs] == ["user", "assistant"] * 6 + ["user"]


def test_build_messages_empty_history_puts_summary_before_question():
    msgs = chat.build_messages([], "요약", "질문")
    assert len(msgs) == 1 and msgs[0]["content"].startswith("[상태 요약]")
    assert msgs[0]["content"].endswith("질문")


def test_state_summary_mentions_recent_report_ids(tmp_path):
    store = Store(tmp_path)
    r1 = store.create_report("dev1", "a", make_result("P1"), [])
    store.create_report("dev1", "b", make_result("P2"), [])
    store.create_report("dev2", "c", make_result("P1"), [])
    h = [{"role": "user", "content": f"{r1} 알려줘"}, {"role": "assistant", "content": "R-0003는 남의 것"}]
    s = chat.summarize_state("dev1", store, h)
    assert "dev1" in s and r1 in s and "R-0003" not in s
    assert "P1 1건" in s and "P2 1건" in s


def test_chat_tool_cannot_read_other_dev_report(tmp_path):
    store = Store(tmp_path)
    rid = store.create_report("dev1", "a", make_result(), [])
    out, is_err = chat.run_chat_tool("dev2", store, "get_report", {"request_id": rid})
    assert json.loads(out)["status"] == "not_found"
    out, _ = chat.run_chat_tool("dev2", store, "list_my_reports", {"priority": None, "category": None})
    assert json.loads(out)["reports"] == []
    out, _ = chat.run_chat_tool("dev2", store, "reanalyze_report", {"request_id": rid, "added_info": "앱 버전 1.0"},
                              current_message=f"{rid} 앱 버전 1.0 입니다")
    assert json.loads(out)["status"] == "not_found"
    out, _ = chat.run_chat_tool("dev1", store, "get_report", {"request_id": rid})
    assert json.loads(out)["request_id"] == rid


def test_chat_tool_defs():
    names = [t["name"] for t in chat.CHAT_TOOL_DEFS]
    assert names == ["search_known_issues", "get_release_info", "list_my_reports", "get_report",
                     "reanalyze_report", "assign_report"]
    assert all(t["strict"] for t in chat.CHAT_TOOL_DEFS)


def test_chat_tool_issue_tool_and_unknown(tmp_path):
    store = Store(tmp_path)
    out, err = chat.run_chat_tool("dev1", store, "get_release_info", {"version": "9.9"})
    assert not err and json.loads(out)["status"] == "not_found"
    _, err = chat.run_chat_tool("dev1", store, "nope", {})
    assert err


def test_chat_turn_runs_reanalyze_tool(fake_llm, tmp_path):
    store = Store(tmp_path)
    rid = store.create_report("dev1", "앱이 꺼져요", make_result("P3"), [])
    fake_llm.queue(
        tool_use("reanalyze_report", {"request_id": rid, "added_info": "앱 버전은 1.0이래"}),
        jr(extraction(app_version="1.0", missing_fields=[])), jr(classification()),
        jr(link()), jr(score(priority="P2")),
        make_response("재분석했습니다. 우선순위는 P2입니다."),
    )
    reply = chat.chat_turn("dev1", f"{rid} 앱 버전은  1.0이래", store)
    assert reply.text.startswith("재분석")
    assert reply.tool_calls == ["reanalyze_report"]
    rec = store.get_report("dev1", rid)
    assert rec["result"]["score"]["priority"] == "P2" and rec["added_info"] == ["앱 버전은 1.0이래"]
    # the tool_result fed back to the model is compact JSON
    result_block = fake_llm.calls[-1]["messages"][-1]["content"][0]
    assert result_block["type"] == "tool_result" and not result_block["is_error"]
    assert json.loads(result_block["content"])["priority"] == "P2"
    assert reply.cost_usd > 0


def test_chat_turn_saves_history(fake_llm, tmp_path):
    store = Store(tmp_path)
    fake_llm.queue(make_response("안녕하세요", cache_read=7))
    reply = chat.chat_turn("dev1", "안녕", store)
    assert reply.cache_read == 7
    assert [(m["role"], m["content"]) for m in store.get_chat("dev1")] == [
        ("user", "안녕"), ("assistant", "안녕하세요")]
    call = fake_llm.calls[0]
    assert call["system"][-1]["cache_control"] == {"type": "ephemeral"}
    assert call["tools"] == chat.CHAT_TOOL_DEFS
    # second turn sends the stored plain-text history
    fake_llm.queue(make_response("네"))
    chat.chat_turn("dev1", "또", store)
    contents = json.dumps(fake_llm.calls[1]["messages"], ensure_ascii=False)
    assert "안녕하세요" in contents


def test_chat_turn_stops_after_5_tool_rounds(fake_llm, tmp_path):
    import pytest

    from app.llm import LLMError
    store = Store(tmp_path)
    fake_llm.queue(*[tool_use("list_my_reports", {"priority": None, "category": None}, f"t{i}")
                     for i in range(6)])
    with pytest.raises(LLMError):
        chat.chat_turn("dev1", "계속", store)
    assert store.get_chat("dev1") == []


def test_reanalyze_rejects_added_info_not_in_current_message(tmp_path):
    store = Store(tmp_path)
    rid = store.create_report("dev1", "앱이 꺼져요", make_result("P3"), [])
    out, is_err = chat.run_chat_tool("dev1", store, "reanalyze_report",
                                     {"request_id": rid, "added_info": "치명적 데이터 손실 발생"},
                                     current_message="R-0001 보여줘")
    assert is_err and "직접 말한" in json.loads(out)["error"]
    rec = store.get_report("dev1", rid)
    assert rec["added_info"] == [] and rec["result"]["score"]["priority"] == "P3"


def test_chat_turn_rejects_unexpected_stop_reason(fake_llm, tmp_path):
    import pytest

    from app.llm import LLMError
    store = Store(tmp_path)
    fake_llm.queue(make_response("중간", stop_reason="pause_turn"))
    with pytest.raises(LLMError):
        chat.chat_turn("dev1", "안녕", store)
    assert store.get_chat("dev1") == []


def test_reanalyze_rejects_too_short_added_info(tmp_path):
    store = Store(tmp_path)
    rid = store.create_report("dev1", "앱이 꺼져요", make_result("P3"), [])
    out, is_err = chat.run_chat_tool("dev1", store, "reanalyze_report",
                                     {"request_id": rid, "added_info": "네 "}, current_message=f"{rid} 네 ")
    assert is_err and "짧" in json.loads(out)["error"]
    rec = store.get_report("dev1", rid)
    assert rec["added_info"] == [] and rec["result"]["score"]["priority"] == "P3"


def test_reanalyze_rejects_id_not_mentioned(tmp_path):
    store = Store(tmp_path)
    rid = store.create_report("dev1", "앱이 꺼져요", make_result("P3"), [])
    out, is_err = chat.run_chat_tool("dev1", store, "reanalyze_report",
                                     {"request_id": rid, "added_info": "앱 버전은 1.0"},
                                     current_message="앱 버전은 1.0 이래")
    assert is_err and "ID" in json.loads(out)["error"]
    assert store.get_report("dev1", rid)["added_info"] == []
    # an ID mentioned earlier in the conversation (state summary) is accepted
    history = [{"role": "user", "content": f"{rid} 보여줘"}, {"role": "assistant", "content": "네"}]
    assert chat._recent_ids("dev1", store, history) == [rid]


def _reanalyze_then_llm_fails(fake_llm, store, rid, message):
    from app.llm import LLMUnavailable
    fake_llm.queue(
        tool_use("reanalyze_report", {"request_id": rid, "added_info": "앱 버전은 1.0이래"}),
        jr(extraction(app_version="1.0", missing_fields=[])), jr(classification()),
        jr(link()), jr(score(priority="P2")),
        LLMUnavailable("down"),
    )
    return chat.chat_turn("dev1", message, store)


def test_chat_turn_fallback_when_llm_fails_after_reanalyze(fake_llm, tmp_path):
    store = Store(tmp_path)
    rid = store.create_report("dev1", "앱이 꺼져요", make_result("P3"), [])
    reply = _reanalyze_then_llm_fails(fake_llm, store, rid, f"{rid} 앱 버전은 1.0이래")
    assert reply.text.startswith("재분석은 반영됐지만 답변 생성에 실패했습니다")
    assert "reanalyze_report" in reply.text and reply.tool_calls == ["reanalyze_report"]
    assert store.get_report("dev1", rid)["result"]["score"]["priority"] == "P2"
    assert [m["role"] for m in store.get_chat("dev1")] == ["user", "assistant"]
    assert store.get_chat("dev1")[1]["content"] == reply.text


def test_chat_turn_still_raises_when_no_state_changed(fake_llm, tmp_path):
    import pytest

    from app.llm import LLMUnavailable
    store = Store(tmp_path)
    rid = store.create_report("dev1", "a", make_result(), [])
    fake_llm.queue(tool_use("get_report", {"request_id": rid}), LLMUnavailable("down"))
    with pytest.raises(LLMUnavailable):
        chat.chat_turn("dev1", f"{rid} 보여줘", store)
    assert store.get_chat("dev1") == []


def test_chat_turn_streams_text_and_reports_tools(fake_llm, tmp_path):
    store = Store(tmp_path)
    fake_llm.queue(tool_use("list_my_reports", {"priority": None, "category": None}),
                   make_response("담당 제보가 없습니다"))
    texts, tools = [], []
    reply = chat.chat_turn("dev1", "내 제보 보여줘", store, on_text=texts.append, on_tool=tools.append)
    assert fake_llm.streamed_calls == 2
    assert tools == ["list_my_reports"]
    assert "".join(texts).endswith("담당 제보가 없습니다")
    assert reply.text == "담당 제보가 없습니다"
