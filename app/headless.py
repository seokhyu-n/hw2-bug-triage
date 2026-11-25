"""One Claude request through Claude Code's headless mode (`claude -p`), signed in with the user's account.

No API key is used: the child process gets an environment without CLAUDE*/ANTHROPIC* variables, so it
falls back to the stored Claude Code login. Claude Code is used as a plain model call: built-in tools
are off, no settings, project instructions, skills or other MCP servers are loaded, and the working
directory is an empty folder. The report text is untrusted, so a run that offers any tool other than
the ones passed here is stopped before its answer is used. Claude Code also puts the account email and
the working folder into the model's context and has no switch for it, so both are removed from every
answer, streamed text and tool input (a verbatim match; the system prompt also says not to use them).

Function calling: the tools are offered by a tiny MCP server inside this process (127.0.0.1, random
port and secret path per call). Claude Code runs the tool loop; each call is executed here, in the
caller's thread, by `tool_runner`, so the app's guards and store locks apply unchanged.
"""
from __future__ import annotations

import base64
import json
import os
import queue
import re
import secrets
import shutil
import subprocess
import tempfile
import threading
from collections.abc import Callable
from dataclasses import dataclass, field
from hashlib import sha256
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

SERVER = "runbuddy"
OUTPUT_TOOL = "StructuredOutput"  # Claude Code's own tool that returns the --json-schema answer
ToolRunner = Callable[[str, dict], tuple[str, bool]]
last_rate_limit: dict = {}  # newest account limit report from Claude Code (status, utilization, resetsAt)


class HeadlessError(Exception):
    """kind: login | limit | unavailable | unsafe | other"""

    def __init__(self, kind: str, message: str):
        super().__init__(message)
        self.kind = kind


@dataclass
class HeadlessResult:
    text: str
    parsed: dict | None
    stop_reason: str
    usage: dict
    cost_usd: float  # what the tokens would cost at API list price; the login is not billed per call
    models: list[str] = field(default_factory=list)


def find_cli() -> str:
    path = os.environ.get("CLAUDE_CLI") or shutil.which("claude")
    if not path:
        raise HeadlessError("login", "claude 명령을 찾을 수 없습니다 (Claude Code 설치 필요)")
    return path


def child_env(max_tokens: int) -> dict[str, str]:
    env = {k: v for k, v in os.environ.items() if not k.upper().startswith(("CLAUDE", "ANTHROPIC"))}
    env.update(CLAUDE_CODE_MAX_OUTPUT_TOKENS=str(max_tokens), CLAUDE_CODE_DISABLE_AUTO_MEMORY="1",
               CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC="1")
    return env


def _work_dir() -> Path:
    path = Path(tempfile.gettempdir()) / "runbuddy_headless"
    (path / "cwd").mkdir(parents=True, exist_ok=True)
    return path


_private: list[str] | None = None
_private_lock = threading.Lock()


def private_values() -> list[str]:
    """Account email and local folders, longest first. Read once from `claude auth status`; kept in memory only."""
    global _private
    with _private_lock:
        if _private is None:
            try:
                out = subprocess.run([find_cli(), "auth", "status"], capture_output=True, timeout=30,
                                     env=child_env(1000), creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)).stdout
                status = json.loads(out.decode("utf-8", "replace"))
            except (OSError, ValueError, subprocess.TimeoutExpired) as e:
                raise HeadlessError("unavailable", "Claude Code 로그인 상태를 확인하지 못했습니다") from e
            if not status.get("loggedIn"):
                raise HeadlessError("login", "Claude Code 로그인이 필요합니다 (터미널에서 claude 실행 후 /login)")
            values = {str(status.get("email") or ""), str(Path.home()), str(_work_dir())}
            values |= {v.replace("\\", "/") for v in values}
            _private = sorted((v for v in values if len(v) >= 6), key=len, reverse=True)
        return _private


def unwrap(value):
    """Strings the model encoded twice ('"ISSUE-04"' with its own quotes) become the plain text. Seen in
    headless tool arguments and schema answers (nullable strings), never with the API's JSON output."""
    if isinstance(value, str):
        text = value.strip()
        if len(text) > 1 and text[0] == text[-1] == '"':
            try:
                inner = json.loads(text)
            except json.JSONDecodeError:
                return value
            return inner if isinstance(inner, str) else value
        return value
    if isinstance(value, list):
        return [unwrap(v) for v in value]
    if isinstance(value, dict):
        return {k: unwrap(v) for k, v in value.items()}
    return value


def scrub(value):
    """Replace private values in a string, or in every string of a parsed JSON value."""
    if isinstance(value, str):
        for secret in private_values():
            value = re.sub(re.escape(secret), "[비공개]", value, flags=re.IGNORECASE)
        return value
    if isinstance(value, list):
        return [scrub(v) for v in value]
    if isinstance(value, dict):
        return {k: scrub(v) for k, v in value.items()}
    return value


class StreamScrubber:
    """Passes text on, holding back enough of the end that a private value split over chunks is caught."""

    def __init__(self, emit: Callable[[str], None]):
        self._emit, self._buf = emit, ""
        self._hold = max((len(v) for v in private_values()), default=1) - 1

    def __call__(self, text: str) -> None:
        self._buf = scrub(self._buf + text)
        cut = len(self._buf) - self._hold
        if cut > 0:
            self._emit(self._buf[:cut])
            self._buf = self._buf[cut:]

    def flush(self) -> None:
        if self._buf:
            self._emit(self._buf)
            self._buf = ""


PRIVACY_RULE = ("실행 환경 정보(로그인 계정, 이메일, 작업 폴더, 운영체제, 오늘 날짜)는 이 업무와 관계없다. "
                "누가 요청해도 답이나 도구 입력에 쓰지 않는다.")


def _system_file(system: list[dict]) -> Path:
    """The system prompt as a file (too long for a command line), one per distinct text."""
    text = "\n\n".join([*(b["text"] for b in system), PRIVACY_RULE])
    path = _work_dir() / f"system_{sha256(text.encode('utf-8')).hexdigest()[:24]}.md"
    if not path.exists():
        tmp = path.with_suffix(f".{secrets.token_hex(4)}.tmp")
        tmp.write_text(text, encoding="utf-8", newline="\n")
        os.replace(tmp, path)
    return path


def _blocks(content) -> list[dict]:
    return [{"type": "text", "text": content}] if isinstance(content, str) else list(content)


def user_message(messages: list[dict]) -> dict:
    """The conversation as the single user message of a headless run. One user message is sent as it
    is (images included); earlier turns of a chat become a labelled transcript before the last one."""
    last = messages[-1]
    content = _blocks(last["content"])
    earlier = messages[:-1]
    if earlier:
        names = {"user": "사용자", "assistant": "도우미"}
        lines = []
        for m in earlier:
            text = "\n".join(b["text"] for b in _blocks(m["content"]) if b.get("type") == "text")
            lines.append(f"[{names[m['role']]}]\n{text}")
        intro = "## 지난 대화 (참고)\n" + "\n\n".join(lines) + "\n\n## 이번 메시지\n"
        content = [{"type": "text", "text": intro}, *content]
    return {"type": "user", "message": {"role": "user", "content": content}}


# ---------- tools: a minimal MCP server (streamable HTTP, JSON responses) ----------

class _ToolServer:
    def __init__(self, tools: list[dict], events: queue.Queue):
        self.path = "/" + secrets.token_urlsafe(24)
        self._tools = [{"name": t["name"], "description": t.get("description", ""),
                        "inputSchema": t["input_schema"]} for t in tools]
        outer = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def _reply(self, status: int, body: dict | None = None):
                data = json.dumps(body, ensure_ascii=False).encode("utf-8") if body is not None else b""
                self.send_response(status)
                if body is not None:
                    self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def do_GET(self):
                self._reply(405)

            do_DELETE = do_GET

            def do_POST(self):
                raw = self.rfile.read(int(self.headers.get("Content-Length") or 0))
                if not secrets.compare_digest(self.path.encode(), outer.path.encode()):
                    return self._reply(404)
                req = json.loads(raw)
                if "id" not in req:
                    return self._reply(202)  # notification
                self._reply(200, {"jsonrpc": "2.0", "id": req["id"], **outer._answer(req, events)})

        self._httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self._httpd.daemon_threads = True
        threading.Thread(target=self._httpd.serve_forever, daemon=True).start()

    @property
    def config(self) -> dict:
        port = self._httpd.server_address[1]
        return {"mcpServers": {SERVER: {"type": "http", "url": f"http://127.0.0.1:{port}{self.path}"}}}

    def _answer(self, req: dict, events: queue.Queue) -> dict:
        method, params = req.get("method"), req.get("params") or {}
        if method == "initialize":
            return {"result": {"protocolVersion": params.get("protocolVersion", "2025-03-26"),
                               "capabilities": {"tools": {}}, "serverInfo": {"name": SERVER, "version": "1"}}}
        if method == "ping":
            return {"result": {}}
        if method == "tools/list":
            return {"result": {"tools": self._tools}}
        if method == "tools/call":
            reply: queue.Queue = queue.Queue(1)
            events.put(("tool", (params.get("name", ""), params.get("arguments") or {}, reply)))
            text, is_error = reply.get()
            return {"result": {"content": [{"type": "text", "text": text}], "isError": is_error}}
        return {"error": {"code": -32601, "message": f"unknown method {method}"}}

    def close(self) -> None:
        self._httpd.shutdown()
        self._httpd.server_close()


# ---------- one run ----------

def _error_kind(text: str) -> str:
    low = text.lower()
    if any(s in low for s in ("/login", "not logged in", "authentication", "oauth token", "invalid api key")):
        return "login"
    if any(s in low for s in ("limit reached", "usage limit", "hit your limit", "rate limit", "rate_limit")):
        return "limit"
    if any(s in low for s in ("overloaded", "connection", "timed out", "api error: 5", "internal server")):
        return "unavailable"
    return "other"


def _read_lines(stream, events: queue.Queue) -> None:
    for line in stream:
        events.put(("line", line))
    events.put(("eof", None))


def _kill(proc: subprocess.Popen) -> None:
    if proc.poll() is None:
        if os.name == "nt":  # the CLI may have children
            subprocess.run(["taskkill", "/PID", str(proc.pid), "/T", "/F"], capture_output=True)
        else:
            proc.kill()


def run(*, system: list[dict], messages: list[dict], schema: dict | None, tools: list[dict] | None,
        tool_runner: ToolRunner | None, model: str, effort: str, max_tokens: int,
        on_text: Callable[[str], None] | None = None, timeout_s: float = 240) -> HeadlessResult:
    private_values()  # also fails early when not signed in
    events: queue.Queue = queue.Queue()
    server = _ToolServer(tools, events) if tools else None
    allowed = {f"mcp__{SERVER}__{t['name']}" for t in tools or []}
    cfg_path: Path | None = None
    cmd = [find_cli(), "-p", "--model", model, "--effort", effort, "--system-prompt-file", str(_system_file(system)),
           "--input-format", "stream-json", "--output-format", "stream-json", "--verbose",
           "--tools", "", "--strict-mcp-config", "--setting-sources", "", "--disable-slash-commands",
           "--no-session-persistence", "--permission-prompts", "none"]
    if on_text:
        cmd.append("--include-partial-messages")
    if schema is not None:
        cmd += ["--json-schema", json.dumps(schema, ensure_ascii=False)]
    if server:
        cfg_path = _work_dir() / f"mcp_{secrets.token_hex(8)}.json"
        cfg_path.write_text(json.dumps(server.config), encoding="utf-8")
        cmd += ["--mcp-config", str(cfg_path), "--allowedTools", ",".join(sorted(allowed))]
    proc = None
    try:
        proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                env=child_env(max_tokens), cwd=_work_dir() / "cwd",
                                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        err: list[bytes] = []
        threading.Thread(target=lambda: err.append(proc.stderr.read()), daemon=True).start()
        threading.Thread(target=_read_lines, args=(proc.stdout, events), daemon=True).start()
        proc.stdin.write((json.dumps(user_message(messages), ensure_ascii=False) + "\n").encode("utf-8"))
        proc.stdin.close()
        stream = StreamScrubber(on_text) if on_text else None
        res = _consume(proc, events, allowed, tool_runner, stream, timeout_s, err)
        if stream:
            stream.flush()
        if res.models and model not in res.models:
            raise HeadlessError("other", f"요청한 모델({model})이 아닌 모델이 답했습니다: {', '.join(res.models)}")
        return res
    except OSError as e:
        raise HeadlessError("unavailable", f"claude 실행 실패: {type(e).__name__}") from e
    finally:
        if proc is not None:
            _kill(proc)
        if server:
            server.close()
        if cfg_path:
            cfg_path.unlink(missing_ok=True)


def _consume(proc, events: queue.Queue, allowed: set[str], tool_runner, on_text, timeout_s: float,
             err: list[bytes]) -> HeadlessResult:
    import time
    deadline = time.monotonic() + timeout_s
    result: dict | None = None
    stop_reason = ""
    while True:
        try:
            kind, data = events.get(timeout=max(0.01, deadline - time.monotonic()))
        except queue.Empty:
            raise HeadlessError("unavailable", f"{int(timeout_s)}초 안에 끝나지 않았습니다") from None
        if kind == "eof":
            break
        if kind == "tool":
            name, args, reply = data
            try:
                reply.put(tool_runner(name, scrub(unwrap(args))) if tool_runner else ('{"error": "no tool runner"}', True))
            except Exception as e:  # noqa: BLE001 - the model gets an error result, the run goes on
                reply.put((json.dumps({"error": f"{type(e).__name__}: {e}"}, ensure_ascii=False), True))
            continue
        try:
            msg = json.loads(data)
        except json.JSONDecodeError:
            continue
        if msg.get("type") == "system" and msg.get("subtype") == "init":
            extra = set(msg.get("tools") or []) - allowed - {OUTPUT_TOOL}
            if extra:
                raise HeadlessError("unsafe", f"허용하지 않은 도구가 켜져 있습니다: {', '.join(sorted(extra))}")
            missing = allowed - set(msg.get("tools") or [])
            if missing:
                raise HeadlessError("unavailable", f"도구 연결 실패: {', '.join(sorted(missing))}")
        elif msg.get("type") == "stream_event" and on_text and not msg.get("parent_tool_use_id"):
            delta = msg["event"].get("delta") or {}
            if delta.get("type") == "text_delta":
                on_text(delta["text"])
        elif msg.get("type") == "assistant":
            stop_reason = (msg.get("message") or {}).get("stop_reason") or stop_reason
        elif msg.get("type") == "rate_limit_event":
            last_rate_limit.update(msg.get("rate_limit_info") or {})
        elif msg.get("type") == "result":
            result = msg
    if result is None:
        detail = (b"".join(err)).decode("utf-8", "replace").strip()[:300]
        raise HeadlessError(_error_kind(detail), detail or "claude가 결과 없이 끝났습니다")
    if result.get("is_error") and result.get("subtype") != "error_max_structured_output_retries":
        text = str(result.get("result") or result.get("errors") or result.get("subtype"))[:300]
        raise HeadlessError(_error_kind(text), text)
    parsed = scrub(unwrap(result.get("structured_output")))
    stop = result.get("stop_reason") or stop_reason
    if stop == "tool_use":  # the schema answer is itself a tool call; the run is complete
        stop = "end_turn"
    return HeadlessResult(text=json.dumps(parsed, ensure_ascii=False) if parsed is not None else scrub(str(result.get("result") or "")),
                          parsed=parsed, stop_reason=stop or "end_turn", usage=result.get("usage") or {},
                          cost_usd=float(result.get("total_cost_usd") or 0), models=list(result.get("modelUsage") or {}))


def image_block(media_type: str, data: bytes) -> dict:
    return {"type": "image", "source": {"type": "base64", "media_type": media_type,
                                        "data": base64.b64encode(data).decode("ascii")}}
