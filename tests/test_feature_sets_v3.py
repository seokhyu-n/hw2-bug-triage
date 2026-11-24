"""The harder feature eval sets (v3): counts, unique ids/texts and gold consistency (no API calls)."""
import json
import re

import pytest

from eval import feature_evals as fe
from eval import feature_sets_v3 as v3

APP_VERSIONS = {"1.0", "1.0.1", "1.1.0", "1.1.1", "1.2.0"}
ISSUES = {i["id"]: i for i in json.loads(
    (fe.EVAL.parent / "data" / "known_issues.json").read_text(encoding="utf-8"))}


def _load(name: str) -> list[dict]:
    return [json.loads(x) for x in (fe.EVAL / name).read_text(encoding="utf-8").splitlines() if x.strip()]


def _squash(s: str) -> str:
    return re.sub(r"\s+", "", s).lower()


@pytest.fixture(scope="module")
def shots():
    return _load("screenshot_cases_v3.jsonl")


@pytest.fixture(scope="module")
def replies():
    return _load("reply_cases_v3.jsonl")


@pytest.fixture(scope="module")
def ios():
    return _load("dataset_ios_v3.jsonl")


def test_files_match_the_generator(shots, replies, ios):
    same = lambda rows: json.loads(json.dumps(rows, ensure_ascii=False))  # noqa: E731 - tuples become lists
    assert shots == same(v3.screenshot_cases())
    assert replies == same(v3.reply_cases())
    assert ios == same(v3.ios_cases())


def test_counts_unique_ids_and_texts(shots, replies, ios):
    for rows, prefix in ((shots, "S3"), (replies, "Q3"), (ios, "I3")):
        assert [r["id"] for r in rows] == [f"{prefix}-{i:03d}" for i in range(1, 101)]
        assert len({_squash(r["text"]) for r in rows}) == 100
    assert len({_squash(r["answer"]) for r in replies}) == 100


def test_texts_are_not_reused_from_the_earlier_sets(shots, replies, ios):
    for rows, old, case in ((shots, "screenshot_cases_v2.jsonl", fe.SCREENSHOT_CASES),
                            (replies, "reply_cases_v2.jsonl", fe.REPLY_CASES), (ios, "dataset_ios_v2.jsonl", [])):
        before = {_squash(r["text"] + r.get("answer", "")) for r in _load(old) + case}
        assert not before & {_squash(r["text"] + r.get("answer", "")) for r in rows}


# ---------- screenshots ----------

def test_screenshot_images_exist_and_are_small(shots):
    names = {f"{c['id']}-{i}.png" for c in shots for i in range(1, len(c["shots"]) + 1)}
    assert {p.name for p in v3.SHOTS3.glob("*.png")} == names
    assert sum(p.stat().st_size for p in v3.SHOTS3.glob("*.png")) < 8_000_000


def test_screenshot_gold_is_drawn_or_written(shots):
    for c in shots:
        assert set(c["expected"]) == {"app_version", "android_version", "device_model"}
        source = c["text"] + json.dumps(c["shots"], ensure_ascii=False)
        for value in c["expected"].values():
            assert value is None or value in source, c["id"]
        assert c["expected"]["app_version"] in APP_VERSIONS | {None}, c["id"]
        if c["actual_has"]:
            assert c["actual_has"] in source, c["id"]


def test_cropped_or_covered_values_are_null_when_nothing_else_shows_them(shots):
    """A value hidden by an effect is expected only when another image or the text gives it."""
    field = {"app": "app_version", "os": "android_version", "dev": "device_model"}
    hide = {"cover", "finger", "blur_key", "mosaic", "cropx", "cropl", "cropy"}
    checked = 0
    for c in shots:
        for _, params in c["shots"]:
            for name, *a in params.get("fx", []):
                if name in hide and a[0] in field:
                    others = [s for s in c["shots"] if s[1] is not params]
                    value = c["expected"][field[a[0]]]
                    checked += 1
                    assert value is None or value in c["text"] + json.dumps(others, ensure_ascii=False), c["id"]
    assert checked >= 15


# ---------- replies ----------

def test_reply_gold_is_stated_by_the_reporter(replies):
    for c in replies:
        assert set(c["expect"]) == {"app_version", "android_version", "device_model"}
        said = _squash(c["text"] + " " + c["answer"])
        for field, value in c["expect"].items():
            if value is not None:
                assert _squash(c.get("written", {}).get(field, value)) in said, (c["id"], field)
        assert c["expect"]["app_version"] in APP_VERSIONS | {None}, c["id"]


def test_reply_set_is_mixed(replies):
    nothing = [c for c in replies if all(v is None for v in c["expect"].values())]
    assert 20 <= len(nothing) <= 40
    assert sum(c["injection"] for c in replies) == 8
    for c in replies:
        if c["injection"]:
            assert "P1" in c["answer"], c["id"]


# ---------- iPhone ----------

def test_ios_platforms_and_links(ios):
    kinds = [c["expected"]["extraction"]["platform"] for c in ios]
    assert kinds.count("ios") == 80 and kinds.count("android") == 20
    for c in ios:
        e, x = c["expected"], c["expected"]["extraction"]
        if x["platform"] == "ios":
            assert x["android_version"] is None and e["linked_issue_id"] is None, c["id"]
        else:
            assert x["ios_version"] is None, c["id"]
        issue = ISSUES.get(e["linked_issue_id"]) if e["linked_issue_id"] else None
        if e["linked_issue_id"]:
            assert x["android_version"] in issue["affected_android"] or f"{x['android_version']}.0" in issue["affected_android"] \
                or x["android_version"].split(".")[0] in issue["affected_android"], c["id"]
            assert x["app_version"] in issue["affected_app_versions"], c["id"]
            assert x["feature_area"] == issue["feature_area"], c["id"]


def test_ios_gold_is_written_in_the_text(ios):
    for c in ios:
        x = c["expected"]["extraction"]
        for field in ("device_model", "android_version", "ios_version", "app_version"):
            assert x[field] is None or _squash(x[field]) in _squash(c["text"]), (c["id"], field)
        assert x["app_version"] in APP_VERSIONS | {None}, c["id"]


def test_ios_categories_and_priorities(ios):
    for c in ios:
        e = c["expected"]
        assert e["labels"] == [e["category"]]
        assert e["category"] in {"bug", "question", "feature_request"} and e["priority"] in {"P1", "P2", "P3", "P4"}
        if e["category"] != "bug":
            assert e["priority"] == "P4" and e["linked_issue_id"] is None, c["id"]
    missing = [c for c in ios if c["expected"]["extraction"]["platform"] == "ios"
               and c["expected"]["extraction"]["ios_version"] is None and c["expected"]["category"] == "bug"]
    assert len(missing) >= 20


# ---------- --set v3 ----------

def test_set_v3_points_the_graders_at_the_v3_files(monkeypatch):
    for name in ("SCREENSHOT_CASES", "SHOTS", "REPLY_CASES", "IOS_PATH"):
        monkeypatch.setattr(fe, name, getattr(fe, name))  # restored after the test
    seen = {}

    def fake(run_id, change):
        seen.update(shots=fe.SHOTS, ios=fe.IOS_PATH, n=(len(fe.SCREENSHOT_CASES), len(fe.REPLY_CASES)),
                    first=fe.SCREENSHOT_CASES[0]["id"] + fe.REPLY_CASES[0]["id"])
        return {"Run ID": run_id, "기능": "", "주 지표": "", "값": "", "보조 지표": ""}

    from eval import run_eval
    monkeypatch.setattr(fe, "run_suggest", fake)
    monkeypatch.setattr(run_eval, "build_xlsx", lambda: None)
    fe.main(["suggest", "--set", "v3"])
    assert seen["shots"].name == "screenshots_v3" and seen["ios"].name == "dataset_ios_v3.jsonl"
    assert seen["n"] == (100, 100) and seen["first"] == "S3-001Q3-001"


def test_review_list_ids_exist(shots, replies, ios):
    ids = {c["id"] for rows in (shots, replies, ios) for c in rows}
    listed = v3.review_list(shots, replies, ios)
    assert listed and all(i in ids and why for i, why in listed)
