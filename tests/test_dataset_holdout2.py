"""dataset_holdout2: 100 harder blind cases (E-401..E-500), written without seeing any model result."""
import json

import pytest

from tests import test_dataset as v1checks

EVAL = v1checks.ROOT / "eval"
HOLDOUT2 = EVAL / "dataset_holdout2.jsonl"


@pytest.fixture(scope="module")
def rows() -> list[dict]:
    return [json.loads(x) for x in HOLDOUT2.read_text(encoding="utf-8").splitlines() if x.strip()]


issues = v1checks.issues
release_versions = v1checks.release_versions

test_enums_and_label_rules = v1checks.test_enums_and_label_rules
test_extraction_fields = v1checks.test_extraction_fields
test_completeness_follows_rubric = v1checks.test_completeness_follows_rubric
test_linked_issues_exist_and_are_consistent = v1checks.test_linked_issues_exist_and_are_consistent
test_tag_consistency = v1checks.test_tag_consistency


def test_utf8_without_bom_and_ids_in_order(rows):
    raw = HOLDOUT2.read_bytes()
    assert not raw.startswith(b"\xef\xbb\xbf") and "\\u" not in raw.decode("utf-8")
    assert [r["id"] for r in rows] == [f"E-{n}" for n in range(401, 501)]


def test_no_text_shared_with_earlier_sets(rows):
    earlier = set()
    for name in ("dataset_v3.jsonl", "dataset_holdout.jsonl"):
        earlier |= {json.loads(x)["text"] for x in (EVAL / name).read_text(encoding="utf-8").splitlines() if x.strip()}
    assert not earlier & {r["text"] for r in rows}


def test_harder_mix(rows):
    labels = [r["expected"]["labels"] for r in rows]
    assert sum(len(x) > 1 for x in labels) >= 20
    assert sum(r["expected"]["linked_issue_id"] is not None for r in rows) >= 12
    assert sum(r["hard"] for r in rows) >= 80
