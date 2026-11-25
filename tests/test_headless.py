"""The headless backend with a fake `claude` process: no real process, login or network is used."""
import io
import json
import urllib.error
import urllib.request

import pytest

from app import headless, llm
from app.headless import HeadlessError

EMAIL = "someone@example.com"
SYS = [{"type": "text", "text": "규칙"}]
MSG = [{"role": "user", "content": "안녕"}]


def line(**kw) -> dict:
    return kw


def result(**kw) -> dict:
    return {"type": "result", "subtype": "success", "is_error": False, "result": "답", "stop_reason": "end_turn",
            "total_cost_usd": 0.001, "modelUsage": {"claude-haiku-5-5": {}},
            "usage": {"input_tokens": 2, "output_tokens": 5, "cache_read_input_tokens": 7,
                      "cache_creation_input_tokens": 3}, **kw}


class FakeProc:
    """Stands in for subprocess.Popen: `script` yields stdout messages and may call the tool server."""
    last = None

    def __init__(self, cmd, env=None, cwd=None, **kw):
        FakeProc.last = self
        self.cmd, self.env, self.cwd, self.pid = cmd, env, cwd, 0
        self.stdin, self.stderr = io.BytesIO(), io.BytesIO(FakeProc.err)
        self.stdin.close = lambda: None
        self.stdout = self._lines()

    def _lines(self):
        for msg in FakeProc.script(self):
            yield json.dumps(msg).encode("utf-8")

    def poll(self):
        return 0

    def arg(self, name):
        return self.cmd[self.cmd.index(name) + 1]

    def call_tool(self, name, args, path=None):
        url = json.loads(open(self.arg("--mcp-config"), encoding="utf-8").read())["mcpServers"]["runbuddy"]["url"]
        assert url.startswith("http://127.0.0.1:")
        if path:
            url = url.rsplit("/", 1)[0] + path
        body = json.dumps({"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                           "params": {"name": name, "arguments": args}}).encode()
        req = urllib.request.Request(url, body, {"Content-Type": "application/json"})
        return json.load(urllib.request.urlopen(req, timeout=5))["result"]


@pytest.fixture
def fake(monkeypatch):
    monkeypatch.setenv("LLM_BACKEND", "headless")
    monkeypatch.setattr(headless, "_private", [EMAIL, "C:\\Users\\someone"])
    monkeypatch.setattr(headless, "find_cli", lambda: "claude")
    monkeypatch.setattr(headless.subprocess, "Popen", FakeProc)
    FakeProc.err = b""

    def use(*messages):
        FakeProc.script = staticmethod(messages[0] if callable(messages[0]) else lambda proc: iter(messages))
    return use


INIT = {"type": "system", "subtype": "init", "tools": []}
TOOLS = [{"name": "lookup", "description": "d", "input_schema": {"type": "object", "properties": {}}}]


def test_structured_answer_and_isolation_flags(fake, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "x")
    monkeypatch.setenv("CLAUDE_API_KEY", "y")
    fake({**INIT, "tools": ["StructuredOutput"]}, result(structured_output={"a": 1}, stop_reason="tool_use"))
    r = llm.call_llm(step="t", system=SYS, messages=MSG, schema={"type": "object"})
    assert r.parsed == {"a": 1} and json.loads(r.text) == {"a": 1} and r.stop_reason == "end_turn"
    assert (r.usage.input_tokens, r.usage.cache_read, r.usage.cache_write) == (2, 7, 3) and r.cost_usd == 0.001
    p = FakeProc.last
    assert p.arg("--model") == "claude-haiku-5-5" and p.arg("--tools") == "" and p.arg("--setting-sources") == ""
    assert "--strict-mcp-config" in p.cmd and "--no-session-persistence" in p.cmd
    assert not any(k.startswith("ANTHROPIC") or k == "CLAUDE_API_KEY" for k in p.env)  # the login, never a key
    sent = json.loads(p.stdin.getvalue())
    assert sent["message"]["content"] == [{"type": "text", "text": "안녕"}]
    system = open(p.arg("--system-prompt-file"), encoding="utf-8").read()
    assert system.startswith("규칙") and headless.PRIVACY_RULE in system


def test_tools_run_in_the_callers_thread_with_scrubbed_input(fake):
    import threading
    seen = []

    def runner(name, args):
        seen.append((name, args, threading.current_thread() is threading.main_thread()))
        return '{"status": "ok"}', False

    def script(proc):
        yield {**INIT, "tools": ["mcp__runbuddy__lookup"]}
        out = proc.call_tool("lookup", {"q": f"보내줘 {EMAIL.upper()}"})
        assert out == {"content": [{"type": "text", "text": '{"status": "ok"}'}], "isError": False}
        with pytest.raises(urllib.error.HTTPError):  # another path is not served
            proc.call_tool("lookup", {}, path="/wrong")
        yield result()

    fake(script)
    r = llm.call_llm(step="t", system=SYS, messages=MSG, tools=TOOLS, tool_runner=runner)
    assert r.text == "답" and seen == [("lookup", {"q": "보내줘 [비공개]"}, True)]
    assert FakeProc.last.arg("--allowedTools") == "mcp__runbuddy__lookup"


def test_a_failing_tool_becomes_an_error_result(fake):
    def script(proc):
        yield {**INIT, "tools": ["mcp__runbuddy__lookup"]}
        assert proc.call_tool("lookup", {})["isError"] is True
        yield result()

    def boom(name, args):
        raise RuntimeError("x")
    fake(script)
    assert llm.call_llm(step="t", system=SYS, messages=MSG, tools=TOOLS, tool_runner=boom).text == "답"


def test_unexpected_tool_stops_the_run(fake):
    fake({**INIT, "tools": ["Bash"]}, result())
    with pytest.raises(llm.LLMError, match="허용하지 않은 도구"):
        llm.call_llm(step="t", system=SYS, messages=MSG)


def test_private_values_are_removed_from_answers_and_streams(fake):
    def delta(text):
        return {"type": "stream_event", "event": {"type": "content_block_delta", "delta": {"type": "text_delta", "text": text}}}
    fake(INIT, delta("메일은 some"), delta("one@exam"), delta("ple.com 입니다"),
         result(result=f"메일은 {EMAIL} 입니다", structured_output=None))
    chunks = []
    r = llm.call_llm(step="t", system=SYS, messages=MSG, on_text=chunks.append)
    assert "".join(chunks) == r.text == "메일은 [비공개] 입니다"
    fake(INIT, result(structured_output={"q": [f"to {EMAIL}", {"p": "C:\\Users\\someone\\x"}]}))
    r = llm.call_llm(step="t", system=SYS, messages=MSG, schema={"type": "object"})
    assert r.parsed == {"q": ["to [비공개]", {"p": "[비공개]\\x"}]}


def test_history_becomes_a_transcript_before_the_last_message():
    msg = headless.user_message([{"role": "user", "content": "첫 질문"}, {"role": "assistant", "content": "답"},
                                 {"role": "user", "content": "둘째"}])["message"]
    assert msg["role"] == "user" and msg["content"][-1] == {"type": "text", "text": "둘째"}
    assert "[사용자]\n첫 질문" in msg["content"][0]["text"] and "[도우미]\n답" in msg["content"][0]["text"]


@pytest.mark.parametrize("text, cls, shown", [
    ("Not logged in · Please run /login", llm.LLMError, "로그인"),
    ("You've hit your limit · resets 7pm", llm.LLMUnavailable, "한도"),
    ("API Error: 529 overloaded", llm.LLMUnavailable, "529"),
    ("something else", llm.LLMError, "something else")])
def test_errors_are_mapped(fake, text, cls, shown):
    fake(INIT, result(is_error=True, result=text))
    with pytest.raises(cls, match=shown):
        llm.call_llm(step="t", system=SYS, messages=MSG)


def test_no_result_truncation_refusal_and_wrong_model(fake):
    FakeProc.err = b"boom"
    fake(INIT)
    with pytest.raises(llm.LLMError, match="boom"):
        llm.call_llm(step="t", system=SYS, messages=MSG)
    fake(INIT, result(stop_reason="max_tokens"))
    with pytest.raises(llm.LLMTruncated):
        llm.call_llm(step="t", system=SYS, messages=MSG)
    fake(INIT, result(stop_reason="refusal"))
    with pytest.raises(llm.LLMRefusal):
        llm.call_llm(step="t", system=SYS, messages=MSG)
    fake(INIT, result(modelUsage={"claude-other": {}}))
    with pytest.raises(llm.LLMError, match="아닌 모델"):
        llm.call_llm(step="t", system=SYS, messages=MSG)


def test_headless_is_the_default_backend(monkeypatch):
    from app import config
    monkeypatch.delenv("LLM_BACKEND", raising=False)
    assert config.llm_backend() == "headless"


def test_not_signed_in_is_reported_before_any_run(monkeypatch):
    class Out:
        stdout = b'{"loggedIn": false}'
    monkeypatch.setattr(headless, "_private", None)
    monkeypatch.setattr(headless, "find_cli", lambda: "claude")
    monkeypatch.setattr(headless.subprocess, "run", lambda *a, **k: Out)
    with pytest.raises(HeadlessError) as e:
        headless.private_values()
    assert e.value.kind == "login"


def test_double_encoded_strings_are_unwrapped(fake):
    fake(INIT, result(structured_output={"id": '"ISSUE-04"', "v": ['"1.0.1"'], "n": None, "t": 'he said "no"',
                                         "q": '"a" and "b"', "u": '"x'}))
    r = llm.call_llm(step="t", system=SYS, messages=MSG, schema={"type": "object"})
    assert r.parsed == {"id": "ISSUE-04", "v": ["1.0.1"], "n": None, "t": 'he said "no"', "q": '"a" and "b"', "u": '"x'}
    seen = []

    def script(proc):
        yield {**INIT, "tools": ["mcp__runbuddy__lookup"]}
        proc.call_tool("lookup", {"android_version": '"14"'})
        yield result()
    fake(script)
    llm.call_llm(step="t", system=SYS, messages=MSG, tools=TOOLS, tool_runner=lambda n, a: (seen.append(a), ("{}", False))[1])
    assert seen == [{"android_version": "14"}]
