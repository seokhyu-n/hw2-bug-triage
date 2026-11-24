"""Builds the fixed (cacheable) system blocks for each pipeline step from prompts/*.md."""
from __future__ import annotations

from functools import lru_cache
from typing import TYPE_CHECKING

from app.config import PROMPTS_DIR

if TYPE_CHECKING:
    from app.pipeline import PipelineConfig

STEPS = ("extract", "classify", "link", "score")
_CACHE = {"type": "ephemeral"}


@lru_cache(maxsize=None)
def load(name: str) -> str | None:
    """Read prompts/<name>.md once (byte-stable across calls); None when the file does not exist."""
    path = PROMPTS_DIR / f"{name}.md"
    return path.read_text(encoding="utf-8").strip() if path.exists() else None


def build_system(step: str, cfg: PipelineConfig) -> list[dict]:
    """Fixed blocks in order: rules -> (few_shot) examples -> (rubric, score only) Rubric.

    Only the last block carries cache_control, so the whole fixed prefix (tools + system) is cached.
    Variable content (report, previous results, tool results) never goes here.
    """
    if step not in STEPS:
        raise ValueError(f"unknown step: {step}")
    texts = [load(step)]
    if cfg.few_shot and (examples := load(f"{step}_fewshot")):
        texts.append(examples)
    if cfg.rubric and step == "score":
        texts.append(load("score_rubric"))
    blocks = [{"type": "text", "text": t} for t in texts]
    blocks[-1]["cache_control"] = dict(_CACHE)
    return blocks


SINGLE_HEADER = (
    "# 한 번에 처리\n"
    "아래 네 작업(추출 → 분류 → 알려진 이슈 연결 → 스코어링)의 규칙을 모두 따르되, 한 번의 응답으로 끝낸다. "
    "이슈 연결이 필요하면(버그일 때) 도구를 호출해 확인한 뒤, 마지막에 네 결과를 하나의 JSON 객체로 출력한다. "
    "버그가 아니면 `link`는 null이다."
)


def build_single_system(cfg: PipelineConfig) -> list[dict]:
    """Ablation without decomposition/chaining: the four steps' rules (and their examples/rubric when
    on) in one system prompt, so the only difference from the chain is doing it in one call."""
    texts = [SINGLE_HEADER]
    for step in STEPS:
        texts.append(load(step))
        if cfg.few_shot and (examples := load(f"{step}_fewshot")):
            texts.append(examples)
    if cfg.rubric:
        texts.append(load("score_rubric"))
    blocks = [{"type": "text", "text": t} for t in texts]
    blocks[-1]["cache_control"] = dict(_CACHE)
    return blocks


def build_chat_system() -> list[dict]:
    """Chatbot system: one fixed block with cache_control (tools + system form the cached prefix)."""
    return [{"type": "text", "text": load("chat"), "cache_control": dict(_CACHE)}]
