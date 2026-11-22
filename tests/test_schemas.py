from app.schemas import Classification, Extraction, Link, Score, TriageResult, to_json_schema


def _walk_objects(node):
    if isinstance(node, dict):
        if node.get("type") == "object":
            yield node
        for v in node.values():
            yield from _walk_objects(v)
    elif isinstance(node, list):
        for v in node:
            yield from _walk_objects(v)


def test_schema_all_required_no_extra():
    s = to_json_schema(Extraction)
    assert set(s["required"]) == set(Extraction.model_fields)
    assert s["additionalProperties"] is False


def test_schema_nested_objects_closed():
    s = to_json_schema(TriageResult)
    objs = list(_walk_objects(s))
    assert len(objs) >= 5
    for o in objs:
        assert o["additionalProperties"] is False
        assert set(o["required"]) == set(o["properties"])


def test_schema_nullable_is_anyof_null():
    s = to_json_schema(Extraction)
    assert s["properties"]["device_model"] == {"anyOf": [{"type": "string"}, {"type": "null"}]}


def test_schema_has_no_unsupported_keywords():
    text = str(to_json_schema(TriageResult))
    for bad in ("'title'", "'default'", "$defs", "$ref"):
        assert bad not in text


def test_score_reasoning_first():
    assert list(to_json_schema(Score)["properties"])[0] == "reasoning"


def test_classification_enum():
    cat = to_json_schema(Classification)["properties"]["category"]
    assert set(cat["enum"]) == {"bug", "question", "feature_request"}


def test_triage_result_roundtrip():
    ext = {k: None for k in ["device_model", "android_version", "app_version", "feature_area",
                             "symptom", "expected", "actual", "frequency"]}
    ext |= {"repro_steps": [], "missing_fields": ["device_model"]}
    data = {
        "extraction": ext,
        "classification": {"category": "bug", "labels": ["bug"], "reason": "r"},
        "link": None,
        "score": {"reasoning": "x", "completeness": None, "priority": "P2", "questions_to_reporter": []},
        "answer_status": "need_info",
    }
    r = TriageResult.model_validate(data)
    assert r.link is None and r.score.priority == "P2"
    assert Link(linked_issue_id=None, match_reason=None, fixed_in=None, user_should_update=None)
