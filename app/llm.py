"""The single Claude call wrapper (Claude Code headless by default, or the API): structured output, usage and cost accounting, error mapping."""
import json
import logging
import time
from collections.abc import Callable
from dataclasses import dataclass

import anthropic

from app import headless
from app.config import MODEL_DEFAULT, PRICES, get_api_key, llm_backend

log = logging.getLogger(__name__)


class LLMError(Exception):
    pass


class LLMRefusal(LLMError):
    pass


class LLMTruncated(LLMError):
    pass


class LLMUnavailable(LLMError):
    pass


@dataclass
class Usage:
    input_tokens: int
    output_tokens: int
    cache_read: int
    cache_write: int


@dataclass
class LLMResult:
    content: list
    text: str
    parsed: dict | None
    stop_reason: str
    usage: Usage
    latency_s: float
    cost_usd: float
    model: str


def cost_usd(model: str, usage: Usage) -> float:
    p = PRICES[model]
    return (usage.input_tokens * p["input"] + usage.output_tokens * p["output"]
            + usage.cache_write * p["cache_write"] + usage.cache_read * p["cache_read"]) / 1_000_000


_client: anthropic.Anthropic | None = None


def get_client() -> anthropic.Anthropic:
    global _client
    if _client is None:
        try:
            key = get_api_key()
        except RuntimeError as e:
            raise LLMError("API 키가 설정되지 않았습니다 (.env의 CLAUDE_API_KEY)") from e
        _client = anthropic.Anthropic(api_key=key)
    return _client


def _send(kwargs: dict, on_text: Callable[[str], None] | None):
    """Non-streaming create(), or messages.stream() when the caller wants text as it is generated."""
    client = get_client()
    if on_text is None:
        return client.messages.create(**kwargs)
    with client.messages.stream(**kwargs) as stream:
        for text in stream.text_stream:
            on_text(text)
        return stream.get_final_message()


_HEADLESS_ERRORS = {"login": (LLMError, "Claude Code 로그인이 필요합니다 (터미널에서 claude 실행 후 /login)"),
                    "limit": (LLMUnavailable, "Claude 사용 한도에 도달했습니다"),
                    "unavailable": (LLMUnavailable, None), "unsafe": (LLMError, None), "other": (LLMError, None)}


def _call_headless(step: str, system, messages, schema, tools, model, effort, max_tokens, on_text,
                   tool_runner) -> "LLMResult":
    start = time.perf_counter()
    try:
        res = headless.run(system=system, messages=messages, schema=schema, tools=tools, tool_runner=tool_runner,
                           model=model, effort=effort, max_tokens=max_tokens, on_text=on_text)
    except headless.HeadlessError as e:
        cls, text = _HEADLESS_ERRORS[e.kind]
        raise cls(text or f"{step}: {e}") from e
    latency = time.perf_counter() - start
    if res.stop_reason == "refusal":
        raise LLMRefusal(f"{step}: 모델이 응답을 거부했습니다")
    if res.stop_reason == "max_tokens":
        raise LLMTruncated(f"{step}: max_tokens({max_tokens})에서 잘렸습니다")
    u = res.usage
    usage = Usage(u.get("input_tokens") or 0, u.get("output_tokens") or 0,
                  u.get("cache_read_input_tokens") or 0, u.get("cache_creation_input_tokens") or 0)
    log.info("llm step=%s backend=headless model=%s in=%d out=%d cr=%d cw=%d latency=%.2fs list_price=$%.6f",
             step, model, usage.input_tokens, usage.output_tokens, usage.cache_read, usage.cache_write,
             latency, res.cost_usd)
    return LLMResult(content=[], text=res.text, parsed=res.parsed, stop_reason=res.stop_reason, usage=usage,
                     latency_s=latency, cost_usd=res.cost_usd, model=model)


def call_llm(*, step: str, system: list[dict], messages: list[dict], schema: dict | None = None,
             tools: list[dict] | None = None, model: str = MODEL_DEFAULT, effort: str = "low",
             max_tokens: int = 4096, stop_sequences: list[str] | None = None,
             on_text: Callable[[str], None] | None = None,
             tool_runner: headless.ToolRunner | None = None) -> LLMResult:
    """One Claude request. With on_text the response is streamed (stream parameter) and each text
    delta is passed to on_text; the returned LLMResult is the same either way.

    Headless: Claude Code runs the whole tool loop and calls tool_runner(name, input) for each tool, so
    the result is always the final turn; cost_usd is the API list price of the tokens, not a charge.
    API: a tool_use turn is returned and the caller runs the tools (tool_runner is not used)."""
    if llm_backend() != "api":
        if stop_sequences:
            raise LLMError(f"{step}: stop_sequences는 헤드리스 모드에서 쓸 수 없습니다")
        return _call_headless(step, system, messages, schema, tools, model, effort, max_tokens, on_text, tool_runner)
    output_config: dict = {"effort": effort}
    if schema is not None:
        output_config["format"] = {"type": "json_schema", "schema": schema}
    kwargs: dict = dict(model=model, max_tokens=max_tokens, system=system, messages=messages,
                        output_config=output_config)
    if tools:
        kwargs["tools"] = tools
        kwargs["tool_choice"] = {"type": "auto"}
    if stop_sequences:
        kwargs["stop_sequences"] = stop_sequences

    start = time.perf_counter()
    try:
        resp = _send(kwargs, on_text)
    except anthropic.AuthenticationError as e:
        raise LLMError("API 키 오류") from e
    except (anthropic.RateLimitError, anthropic.APIConnectionError) as e:
        raise LLMUnavailable(f"{type(e).__name__}") from e
    except anthropic.APIStatusError as e:
        if e.status_code >= 500:
            raise LLMUnavailable(f"HTTP {e.status_code}") from e
        raise LLMError(f"API 오류 {e.status_code}: {e.message}") from e
    except anthropic.APIError as e:
        raise LLMError(f"API 오류: {type(e).__name__}") from e
    latency = time.perf_counter() - start

    if resp.stop_reason == "refusal":
        raise LLMRefusal(f"{step}: 모델이 응답을 거부했습니다")
    if resp.stop_reason == "max_tokens":
        raise LLMTruncated(f"{step}: max_tokens({max_tokens})에서 잘렸습니다")

    u = resp.usage
    usage = Usage(u.input_tokens or 0, u.output_tokens or 0,
                  getattr(u, "cache_read_input_tokens", 0) or 0,
                  getattr(u, "cache_creation_input_tokens", 0) or 0)
    texts = [b.text for b in resp.content if b.type == "text"]
    parsed = None
    if texts:
        try:
            parsed = json.loads(texts[-1])
        except json.JSONDecodeError:
            parsed = None
    cost = cost_usd(model, usage)
    log.info("llm step=%s model=%s in=%d out=%d cr=%d cw=%d latency=%.2fs cost=$%.6f",
             step, model, usage.input_tokens, usage.output_tokens, usage.cache_read, usage.cache_write,
             latency, cost)
    return LLMResult(content=list(resp.content), text="".join(texts), parsed=parsed,
                     stop_reason=resp.stop_reason, usage=usage, latency_s=latency, cost_usd=cost, model=model)
