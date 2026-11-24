"""dataset_holdout: 100 new cases (E-301..E-400) written without seeing the V3 prompt tuning."""
import json

import pytest

from tests import test_dataset as v1checks

HOLDOUT = v1checks.ROOT / "eval" / "dataset_holdout.jsonl"
V3 = v1checks.ROOT / "eval" / "dataset_v3.jsonl"


@pytest.fixture(scope="module")
def rows() -> list[dict]:
    return [json.loads(x) for x in HOLDOUT.read_text(encoding="utf-8").splitlines() if x.strip()]


issues = v1checks.issues
release_versions = v1checks.release_versions

test_enums_and_label_rules = v1checks.test_enums_and_label_rules
test_extraction_fields = v1checks.test_extraction_fields
test_completeness_follows_rubric = v1checks.test_completeness_follows_rubric
test_linked_issues_exist_and_are_consistent = v1checks.test_linked_issues_exist_and_are_consistent
test_tag_consistency = v1checks.test_tag_consistency


def test_ids_and_no_text_shared_with_v3(rows):
    assert [r["id"] for r in rows] == [f"E-{n}" for n in range(301, 401)]
    v3 = {json.loads(x)["text"] for x in V3.read_text(encoding="utf-8").splitlines() if x.strip()}
    assert not v3 & {r["text"] for r in rows}
