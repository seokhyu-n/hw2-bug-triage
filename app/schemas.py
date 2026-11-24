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


class ScoreDirect(BaseModel):
    """Ablation without chain-of-thought: the verdict fields only, no reasoning written first."""
    completeness: Literal[0, 1, 2] | None
    priority: Literal["P1", "P2", "P3", "P4"]
    questions_to_reporter: list[str]


class SingleResult(BaseModel):
    """Ablation without decomposition: all four step outputs from one call."""
    extraction: Extraction
    classification: Classification
    link: Link | None
    score: Score


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


def strip_null_strings(schema: Any) -> Any:
    """Copy of a schema where every nullable string ({string | null}) is a plain string ("" = unknown).
    The API limits union-typed parameters per schema; the one-call ablation schema (all four steps in
    one object) exceeds it, so its optional strings are sent as plain strings and "" (or the text "null",
    which the model also writes) is read back as null."""
    if isinstance(schema, list):
        return [strip_null_strings(n) for n in schema]
    if not isinstance(schema, dict):
        return schema
    alts = schema.get("anyOf")
    if alts and len(alts) == 2 and {"type": "null"} in alts:
        other = next(a for a in alts if a != {"type": "null"})
        if other.get("type") == "string":
            return {**strip_null_strings(other), "x-nullable": True}
    return {k: strip_null_strings(v) for k, v in schema.items()}


def empty_to_null(data: Any, schema: Any) -> Any:
    """Undo strip_null_strings on a parsed response: "" in a nullable-string slot becomes None."""
    if isinstance(schema, dict) and schema.get("anyOf"):  # e.g. link: object | null
        obj = next((a for a in schema["anyOf"] if a.get("type") == "object"), None)
        return empty_to_null(data, obj) if obj and isinstance(data, dict) else data
    if isinstance(data, dict) and isinstance(schema, dict):
        props = schema.get("properties", {})
        return {k: empty_to_null(v, props.get(k, {})) for k, v in data.items()}
    if isinstance(data, list) and isinstance(schema, dict):
        return [empty_to_null(v, schema.get("items", {})) for v in data]
    if (isinstance(data, str) and data.strip().lower() in ("", "null", "none")
            and isinstance(schema, dict) and schema.get("x-nullable")):
        return None
    return data


def wire_schema(schema: Any) -> Any:
    """Drop the private x-nullable marker before sending."""
    if isinstance(schema, list):
        return [wire_schema(n) for n in schema]
    if not isinstance(schema, dict):
        return schema
    return {k: wire_schema(v) for k, v in schema.items() if k != "x-nullable"}

