"""dataset_v2 = dataset_v1 (unchanged) + 20 hard classification cases; same label rules as v1."""
import json
from collections import Counter

import pytest

from tests import test_dataset as v1checks

V2 = v1checks.ROOT / "eval" / "dataset_v2.jsonl"


@pytest.fixture(scope="module")
def raw_bytes() -> bytes:
    return V2.read_bytes()


@pytest.fixture(scope="module")
def rows(raw_bytes) -> list[dict]:
    return [json.loads(line) for line in raw_bytes.decode("utf-8").splitlines() if line.strip()]


issues = v1checks.issues
release_versions = v1checks.release_versions

# the v1 structural / label-rule checks, applied to all 120 rows
test_enums_and_label_rules = v1checks.test_enums_and_label_rules
test_extraction_fields = v1checks.test_extraction_fields
test_completeness_follows_rubric = v1checks.test_completeness_follows_rubric
test_linked_issues_exist_and_are_consistent = v1checks.test_linked_issues_exist_and_are_consistent
test_tag_consistency = v1checks.test_tag_consistency


def test_file_ids_and_shape(raw_bytes, rows):
    assert not raw_bytes.startswith(b"\xef\xbb\xbf")
    assert "\\u" not in raw_bytes.decode("utf-8")  # written with ensure_ascii=False
    assert [r["id"] for r in rows] == [f"E-{n:03d}" for n in range(1, 121)]
    assert len({r["text"] for r in rows}) == 120
    for r in rows:
        assert set(r) == {"id", "text", "hard", "tags", "expected"}, r["id"]
        assert set(r["tags"]) <= v1checks.TAGS, r["id"]


def test_v1_is_an_unchanged_prefix(raw_bytes):
    v1 = v1checks.DATASET.read_text(encoding="utf-8").splitlines()
    v2 = raw_bytes.decode("utf-8").splitlines()
    assert len(v2) == 120 and v2[:100] == v1


def test_new_cases_are_hard_classification_boundaries(rows):
    new = rows[100:]
    assert [r["id"] for r in new] == [f"E-{i}" for i in range(101, 121)]
    assert all(r["hard"] for r in new)
    cats = Counter(r["expected"]["category"] for r in new)
    assert cats["bug"] >= 8 and cats["question"] >= 5 and cats["feature_request"] >= 5
    boundary = {"boundary_bug_question", "boundary_bug_feature", "mixed_labels", "injection_attempt"}
    assert all(boundary & set(r["tags"]) for r in new)
