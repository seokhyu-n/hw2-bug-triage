"""Pydantic models for the triage pipeline and the JSON-schema generator for structured output."""
from typing import Any, Literal

from pydantic import BaseModel

Category = Literal["bug", "question", "feature_request"]


class Extraction(BaseModel):
    device_model: str | None
    # from the text (갤럭시/안드로이드 vs 아이폰/iOS), else null. Defaults keep reports saved before
    # iOS support loadable; the JSON schema still requires every field (to_json_schema).
    platform: Literal["android", "ios"] | None = None
    android_version: str | None
    ios_version: str | None = None
    app_version: str | None
    feature_area: str | None
    symptom: str | None
    expected: str | None
    actual: str | None
    frequency: str | None
    repro_steps: list[str]
    missing_fields: list[str]


class Classification(BaseModel):
    category: Category
    labels: list[Category]
    reason: str


class Link(BaseModel):
    linked_issue_id: str | None
    match_reason: str | None
    fixed_in: str | None
    user_should_update: bool | None


class Score(BaseModel):
    reasoning: str  # chain-of-thought first, before the verdict fields
    completeness: Literal[0, 1, 2] | None
    priority: Literal["P1", "P2", "P3", "P4"]
    questions_to_reporter: list[str]


class TriageResult(BaseModel):
    extraction: Extraction
    classification: Classification
    link: Link | None
    score: Score
    answer_status: Literal["ready", "need_info"]


_DROP_KEYS = {"title", "default", "description", "examples"}


def _clean(node: Any, defs: dict) -> Any:
    if isinstance(node, list):
        return [_clean(n, defs) for n in node]
    if not isinstance(node, dict):
        return node
    if "$ref" in node:
        return _clean(defs[node["$ref"].split("/")[-1]], defs)
    out = {k: _clean(v, defs) for k, v in node.items() if k not in _DROP_KEYS and k != "$defs"}
    if out.get("type") == "object":
        props = out.get("properties", {})
        out["required"] = list(props)
        out["additionalProperties"] = False
    return out


def to_json_schema(model: type[BaseModel]) -> dict:
    """Inline $refs, drop unsupported keywords, require every field, close every object."""
    raw = model.model_json_schema()
    return _clean(raw, raw.get("$defs", {}))
