from types import SimpleNamespace as NS

import anthropic
import httpx2 as httpx
import pytest

from app import llm
from app.llm import LLMError, LLMRefusal, LLMTruncated, LLMUnavailable, Usage, call_llm
from tests.conftest import make_response

SYS = [{"type": "text", "text": "sys"}]
MSG = [{"role": "user", "content": "hi"}]


def test_cost_haiku():
    u = Usage(1_000_000, 1_000_000, 0, 0)
    assert llm.cost_usd("claude-haiku-5-5", u) == pytest.approx(0.60)


def test_cost_includes_cache():
    u = Usage(0, 0, 1_000_000, 1_000_000)
    assert llm.cost_usd("claude-haiku-5-5", u) == pytest.approx(0.135)


def test_call_parses_json(fake_llm):
    fake_llm.queue(make_response('{"a":1}'))
    r = call_llm(step="t", system=SYS, messages=MSG)
    assert r.parsed == {"a": 1}
    assert r.cost_usd > 0
    assert r.usage == Usage(100, 50, 0, 0)
    assert r.model == "claude-haiku-5-5"


def test_none_cache_tokens_are_zero(fake_llm):
    fake_llm.queue(make_response("x", cache_read=None, cache_write=None))
    r = call_llm(step="t", system=SYS, messages=MSG)
    assert r.usage.cache_read == 0 and r.usage.cache_write == 0
    assert r.parsed is None


def test_call_sends_schema_and_effort(fake_llm):
    fake_llm.queue(make_response('{"a":1}'))
    call_llm(step="t", system=SYS, messages=MSG, schema={"type": "object"})
    kw = fake_llm.calls[0]
    assert kw["output_config"]["format"]["type"] == "json_schema"
    assert kw["output_config"]["format"]["schema"] == {"type": "object"}
    assert kw["output_config"]["effort"] == "low"
    for banned in ("thinking", "temperature", "tools", "tool_choice", "stop_sequences"):
        assert banned not in kw


def test_no_schema_only_effort(fake_llm):
    fake_llm.queue(make_response("hello"))
    call_llm(step="t", system=SYS, messages=MSG, effort="medium")
    assert fake_llm.calls[0]["output_config"] == {"effort": "medium"}


def test_call_uses_auto_tool_choice(fake_llm):
    fake_llm.queue(make_response("x"))
    call_llm(step="t", system=SYS, messages=MSG, tools=[{"name": "t"}])
    kw = fake_llm.calls[0]
    assert kw["tool_choice"] == {"type": "auto"} and kw["tools"] == [{"name": "t"}]


def test_stop_sequences_passed_only_when_given(fake_llm):
    fake_llm.queue(make_response("x"))
    call_llm(step="t", system=SYS, messages=MSG, stop_sequences=["END"])
    assert fake_llm.calls[0]["stop_sequences"] == ["END"]


def test_thinking_blocks_skipped(fake_llm):
    content = [NS(type="thinking", thinking="hmm"), NS(type="text", text="a"), NS(type="text", text='{"k":2}')]
    fake_llm.queue(make_response(content=content))
    r = call_llm(step="t", system=SYS, messages=MSG)
    assert r.text == 'a{"k":2}' and r.parsed == {"k": 2}


def test_bad_json_gives_none_parsed(fake_llm):
    fake_llm.queue(make_response("not json"))
    assert call_llm(step="t", system=SYS, messages=MSG, schema={"type": "object"}).parsed is None


def test_call_raises_on_refusal(fake_llm):
    fake_llm.queue(make_response("", stop_reason="refusal"))
    with pytest.raises(LLMRefusal):
        call_llm(step="t", system=SYS, messages=MSG)


def test_call_raises_on_max_tokens(fake_llm):
    fake_llm.queue(make_response("{", stop_reason="max_tokens"))
    with pytest.raises(LLMTruncated):
        call_llm(step="t", system=SYS, messages=MSG)


def _status_err(cls, code):
    req = httpx.Request("POST", "https://api.anthropic.com/v1/messages")
    return cls("boom", response=httpx.Response(code, request=req), body=None)


def test_auth_error_is_llmerror(fake_llm):
    fake_llm.queue(_status_err(anthropic.AuthenticationError, 401))
    with pytest.raises(LLMError, match="API 키 오류") as e:
        call_llm(step="t", system=SYS, messages=MSG)
    assert not isinstance(e.value, LLMUnavailable)


@pytest.mark.parametrize("cls,code", [(anthropic.RateLimitError, 429), (anthropic.InternalServerError, 500)])
def test_unavailable(fake_llm, cls, code):
    fake_llm.queue(_status_err(cls, code))
    with pytest.raises(LLMUnavailable):
        call_llm(step="t", system=SYS, messages=MSG)


def test_connection_error_unavailable(fake_llm):
    req = httpx.Request("POST", "https://api.anthropic.com/v1/messages")
    fake_llm.queue(anthropic.APIConnectionError(request=req))
    with pytest.raises(LLMUnavailable):
        call_llm(step="t", system=SYS, messages=MSG)


def test_missing_api_key_becomes_llm_error(monkeypatch):
    import pytest

    from app import llm

    def no_key():
        raise RuntimeError("missing")
    monkeypatch.setattr(llm, "_client", None)
    monkeypatch.setattr(llm, "get_api_key", no_key)
    with pytest.raises(llm.LLMError, match="API 키가 설정되지 않았습니다"):
        llm.call_llm(step="x", system=[], messages=[])


def test_other_sdk_errors_become_llm_error(fake_llm):
    import httpx
    import pytest

    from app import llm
    fake_llm.queue(anthropic.APIError("weird", httpx.Request("POST", "http://x"), body=None))
    with pytest.raises(llm.LLMError, match="API 오류"):
        llm.call_llm(step="x", system=[], messages=[])


def test_stream_path_calls_on_text_and_returns_same_result(fake_llm):
    fake_llm.queue(make_response('{"a": 1}', cache_read=5))
    chunks = []
    res = call_llm(step="t", system=[], messages=[], on_text=chunks.append)
    assert fake_llm.streamed_calls == 1
    assert "".join(chunks) == '{"a": 1}' and len(chunks) == 2
    assert res.parsed == {"a": 1} and res.usage.cache_read == 5 and res.cost_usd > 0


def test_no_on_text_uses_create(fake_llm):
    fake_llm.queue(make_response("{}"))
    call_llm(step="t", system=[], messages=[])
    assert fake_llm.streamed_calls == 0


def test_stream_refusal_still_raises(fake_llm):
    fake_llm.queue(make_response("", stop_reason="refusal"))
    with pytest.raises(LLMRefusal):
        call_llm(step="t", system=[], messages=[], on_text=lambda t: None)
