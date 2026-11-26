"""dataset_v3 = dataset_v2 (unchanged) + 130 hard cases (E-121..E-250); same label rules as v1."""
import json
from collections import Counter

import pytest

from tests import test_dataset as v1checks

V3 = v1checks.ROOT / "eval" / "dataset_v3.jsonl"
V2 = v1checks.ROOT / "eval" / "dataset_v2.jsonl"


@pytest.fixture(scope="module")
def raw_bytes() -> bytes:
    return V3.read_bytes()


@pytest.fixture(scope="module")
def rows(raw_bytes) -> list[dict]:
    return [json.loads(line) for line in raw_bytes.decode("utf-8").splitlines() if line.strip()]


issues = v1checks.issues
release_versions = v1checks.release_versions

test_enums_and_label_rules = v1checks.test_enums_and_label_rules
test_extraction_fields = v1checks.test_extraction_fields
test_completeness_follows_rubric = v1checks.test_completeness_follows_rubric
test_linked_issues_exist_and_are_consistent = v1checks.test_linked_issues_exist_and_are_consistent
test_tag_consistency = v1checks.test_tag_consistency


def test_file_ids_and_shape(raw_bytes, rows):
    assert not raw_bytes.startswith(b"\xef\xbb\xbf")
    assert [r["id"] for r in rows] == [f"E-{n:03d}" for n in range(1, 251)]
    assert len({r["text"] for r in rows}) == 250
    for r in rows:
        assert set(r) == {"id", "text", "hard", "tags", "expected"}, r["id"]
        assert set(r["tags"]) <= v1checks.TAGS, r["id"]


def test_v2_is_an_unchanged_prefix_except_listed_label_fixes(raw_bytes):
    from eval.build_dataset_v3 import V2_LABEL_FIXES
    v2 = V2.read_text(encoding="utf-8").splitlines()
    v3 = raw_bytes.decode("utf-8").splitlines()[:120]
    for old, new in zip(v2, v3):
        if old == new:
            continue
        a, b = json.loads(old), json.loads(new)
        assert a["id"] in V2_LABEL_FIXES, a["id"]  # only a documented human label fix may differ
        assert b["expected"] == {**a["expected"], **V2_LABEL_FIXES[a["id"]]}
        assert {k: v for k, v in a.items() if k != "expected"} == {k: v for k, v in b.items() if k != "expected"}
    assert len(v3) == len(v2)


def test_new_cases_are_hard_and_cover_every_task(rows):
    new = [r["expected"] for r in rows[120:]]
    assert sum(r["hard"] for r in rows[120:]) >= 100
    assert Counter(e["category"] for e in new)["question"] >= 15
    assert Counter(e["category"] for e in new)["feature_request"] >= 15
    assert all(Counter(e["priority"] for e in new)[p] >= 10 for p in ("P1", "P2", "P3"))
    assert sum(1 for e in new if e["linked_issue_id"]) >= 20
    assert sum(len(e["labels"]) > 1 for e in new) >= 10
