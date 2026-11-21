"""Structural and label-consistency checks for the fixed evaluation dataset eval/dataset_v1.jsonl."""
import json
import re
from collections import Counter
from pathlib import Path
from typing import get_args

import pytest

from app.schemas import Category, Extraction
from app.tools import parse_version

ROOT = Path(__file__).resolve().parent.parent
DATASET = ROOT / "eval" / "dataset_v1.jsonl"
DATA = ROOT / "data"

CATEGORIES = set(get_args(Category))
FEATURE_AREAS = {"tracking", "map", "record", "card_image", "voice", "login", "ai_chat", "other"}
PRIORITIES = {"P1", "P2", "P3", "P4"}
LABEL_EXTRACTION_FIELDS = set(Extraction.model_fields) - {"missing_fields"}  # missing_fields is computed in code
REQUIRED_FIELDS = ("app_version", "android_version", "repro_steps")
TAGS = {"missing", "boundary_bug_question", "boundary_bug_feature", "mixed_labels", "known_issue_match",
        "known_issue_near_miss", "already_fixed_version", "version_variant", "vague", "crash",
        "injection_attempt"}


@pytest.fixture(scope="module")
def raw_bytes() -> bytes:
    return DATASET.read_bytes()


@pytest.fixture(scope="module")
def rows(raw_bytes) -> list[dict]:
    return [json.loads(line) for line in raw_bytes.decode("utf-8").splitlines() if line.strip()]


@pytest.fixture(scope="module")
def issues() -> dict[str, dict]:
    return {i["id"]: i for i in json.loads((DATA / "known_issues.json").read_text(encoding="utf-8"))}


@pytest.fixture(scope="module")
def release_versions() -> set:
    return {parse_version(r["version"]) for r in json.loads((DATA / "releases.json").read_text(encoding="utf-8"))}


def _missing_required(ext: dict) -> int:
    return sum(1 for f in REQUIRED_FIELDS if ext[f] in (None, []))


def test_file_is_utf8_jsonl_without_bom(raw_bytes):
    assert not raw_bytes.startswith(b"\xef\xbb\xbf")
    lines = raw_bytes.decode("utf-8").splitlines()
    assert len(lines) == 100
    assert all(line.strip() for line in lines)
    assert "\\u" not in raw_bytes.decode("utf-8")  # written with ensure_ascii=False


def test_ids_sequential_and_unique(rows):
    assert [r["id"] for r in rows] == [f"E-{n:03d}" for n in range(1, 101)]


def test_row_shape(rows):
    for r in rows:
        assert set(r) == {"id", "text", "hard", "tags", "expected"}, r["id"]
        assert isinstance(r["text"], str) and r["text"].strip()
        assert isinstance(r["hard"], bool)
        assert set(r["tags"]) <= TAGS, r["id"]
        assert set(r["expected"]) == {"category", "labels", "extraction", "completeness", "priority",
                                      "linked_issue_id"}, r["id"]
    assert len({r["text"] for r in rows}) == 100  # no duplicate texts


def test_enums_and_label_rules(rows):
    for r in rows:
        e = r["expected"]
        assert e["category"] in CATEGORIES, r["id"]
        assert set(e["labels"]) <= CATEGORIES and len(set(e["labels"])) == len(e["labels"]), r["id"]
        assert e["category"] in e["labels"], r["id"]
        if "bug" in e["labels"]:
            assert e["category"] == "bug", r["id"]  # bug is primary whenever present
        assert e["priority"] in PRIORITIES, r["id"]
        if "bug" in e["labels"]:
            assert e["completeness"] in (0, 1, 2), r["id"]
        else:
            assert e["completeness"] is None, r["id"]
            assert e["priority"] == "P4", r["id"]  # general question / request
            assert e["linked_issue_id"] is None, r["id"]


def test_extraction_fields(rows, release_versions):
    for r in rows:
        ext = r["expected"]["extraction"]
        assert set(ext) == LABEL_EXTRACTION_FIELDS, r["id"]
        assert isinstance(ext["repro_steps"], list) and all(isinstance(s, str) and s for s in ext["repro_steps"])
        for f in LABEL_EXTRACTION_FIELDS - {"repro_steps"}:
            assert ext[f] is None or (isinstance(ext[f], str) and ext[f].strip()), (r["id"], f)
        assert ext["feature_area"] is None or ext["feature_area"] in FEATURE_AREAS, r["id"]
        # no inferred values: device/version strings must literally appear in the report text
        for f in ("device_model", "android_version", "app_version", "frequency"):
            if ext[f] is not None:
                assert ext[f] in r["text"], (r["id"], f, ext[f])
        if ext["app_version"] is not None:
            assert parse_version(ext["app_version"]) in release_versions, r["id"]
        if ext["android_version"] is not None:
            assert re.fullmatch(r"\d+(\.\d+){0,2}", ext["android_version"]), r["id"]


def test_completeness_follows_rubric(rows):
    for r in rows:
        e, ext = r["expected"], r["expected"]["extraction"]
        if e["completeness"] == 2:
            assert _missing_required(ext) == 0, r["id"]
        elif e["completeness"] is not None and _missing_required(ext) == 0:
            assert e["completeness"] == 0, r["id"]  # everything present but symptom unclear


def test_linked_issues_exist_and_are_consistent(rows, issues):
    for r in rows:
        e, ext = r["expected"], r["expected"]["extraction"]
        link = e["linked_issue_id"]
        assert ("known_issue_match" in r["tags"]) == (link is not None), r["id"]
        if link is None:
            continue
        assert link in issues, r["id"]
        assert "bug" in e["labels"], r["id"]
        issue = issues[link]
        if ext["app_version"] is not None:
            assert parse_version(ext["app_version"]) in {parse_version(v) for v in issue["affected_app_versions"]}, r["id"]
        if ext["android_version"] is not None:
            av = ext["android_version"]
            assert any(av == a or av.startswith(a + ".") or av.split(".")[0] == a for a in issue["affected_android"]), r["id"]
        if ext["feature_area"] is not None:
            assert ext["feature_area"] == issue["feature_area"], r["id"]


def test_tag_consistency(rows):
    for r in rows:
        e = r["expected"]
        is_bug = "bug" in e["labels"]
        assert ("missing" in r["tags"]) == (is_bug and _missing_required(e["extraction"]) >= 2), r["id"]
        assert ("mixed_labels" in r["tags"]) == (len(e["labels"]) > 1), r["id"]
        if "known_issue_near_miss" in r["tags"]:
            assert e["linked_issue_id"] is None, r["id"]
        if "vague" in r["tags"] and is_bug and "crash" not in r["tags"]:
            assert e["completeness"] == 0, r["id"]


def test_distribution_minimums(rows):
    cats = Counter(r["expected"]["category"] for r in rows)
    assert all(cats[c] >= 20 for c in CATEGORIES), cats
    assert sum(r["hard"] for r in rows) >= 10
    assert sum("missing" in r["tags"] for r in rows) >= 15
    assert sum(len(r["expected"]["labels"]) > 1 for r in rows) >= 8
    assert sum("injection_attempt" in r["tags"] for r in rows) >= 3
    assert len({r["expected"]["linked_issue_id"] for r in rows} - {None}) >= 10  # most known issues covered
    assert {r["expected"]["priority"] for r in rows} == PRIORITIES
    assert {r["expected"]["completeness"] for r in rows} == {0, 1, 2, None}


def test_check_dataset_summary(rows):
    from eval.check_dataset import summarize
    s = summarize(rows)
    assert s["total"] == 100
    assert sum(s["category"].values()) == 100
    assert sum(s["priority"].values()) == 100
