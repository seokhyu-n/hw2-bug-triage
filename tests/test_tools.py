import json

import pytest

from app import tools
from app.config import DATA_DIR


@pytest.mark.parametrize("text,expected", [
    ("1.0", (1, 0, 0)), ("v1.0.1", (1, 0, 1)), ("1.0.1 버전", (1, 0, 1)),
    ("최신", None), (None, None), ("", None)])
def test_parse_version_variants(text, expected):
    assert tools.parse_version(text) == expected


def test_version_lt_unknown_is_none():
    assert tools.version_lt("최신", "1.0.1") is None


def test_version_lt_basic():
    assert tools.version_lt("1.0", "1.0.1") is True
    assert tools.version_lt("1.1.0", "1.0.1") is False


def test_search_finds_android14_crash():
    r = tools.search_known_issues(["크래시", "시작"], feature_area="tracking", android_version="14")
    assert r["status"] == "ok"
    assert r["issues"][0]["id"] == "ISSUE-02"
    assert len(r["issues"]) <= 5


def test_search_filters_without_keyword_hit_not_found():
    r = tools.search_known_issues(["존재하지않는단어xyz"], feature_area="tracking", android_version="14")
    assert r["status"] == "not_found"


def test_search_empty_keywords_uses_filters():
    r = tools.search_known_issues([], feature_area="voice")
    assert r["status"] == "ok" and r["issues"][0]["id"] == "ISSUE-10"


def test_search_not_found():
    assert tools.search_known_issues(["존재하지않는단어xyz"])["status"] == "not_found"


def test_release_found_and_not_found():
    r = tools.get_release_info("1.1.0")
    assert r["status"] == "ok" and "ISSUE-01" in r["fixed_issues"]
    assert tools.get_release_info("9.9.9")["status"] == "not_found"


def test_run_tool_unknown_name_is_error():
    assert tools.run_tool("nope", {})[1] is True


def test_run_tool_ok_and_exception():
    out, err = tools.run_tool("get_release_info", {"version": "1.0"})
    assert err is False and json.loads(out)["status"] == "ok"
    assert tools.run_tool("get_release_info", {})[1] is True


def test_tool_defs_strict():
    for d in tools.ISSUE_TOOL_DEFS:
        assert d["strict"] is True
        s = d["input_schema"]
        assert s["additionalProperties"] is False
        assert set(s["required"]) == set(s["properties"])


def test_data_consistency():
    issues = json.loads((DATA_DIR / "known_issues.json").read_text(encoding="utf-8"))
    rels = {r["version"]: r for r in json.loads((DATA_DIR / "releases.json").read_text(encoding="utf-8"))}
    assert len(issues) == 12
    assert sum(i["status"] == "open" for i in issues) >= 3
    for i in issues:
        if i["fixed_in"]:
            assert i["fixed_in"] in rels and i["id"] in rels[i["fixed_in"]]["fixed_issues"]
    ids = {i["id"] for i in issues}
    for r in rels.values():
        for f in r["fixed_issues"]:
            assert f in ids
