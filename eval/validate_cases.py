r"""Check a JSONL file of new eval cases against the dataset label rules (same checks as tests/test_dataset.py).

    venv\Scripts\python.exe -m eval.validate_cases eval\dataset_v3_new_a.jsonl
Prints OK or the first failing rule with the case id. Used while writing dataset_v3 cases.
"""
import json
import sys
from pathlib import Path

from tests import test_dataset as rules


def load(path: Path) -> list[dict]:
    return [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines() if x.strip()]


def validate(rows: list[dict]) -> list[str]:
    issues = {i["id"]: i for i in json.loads((rules.DATA / "known_issues.json").read_text(encoding="utf-8"))}
    releases = {rules.parse_version(r["version"])
                for r in json.loads((rules.DATA / "releases.json").read_text(encoding="utf-8"))}
    problems = []
    checks = [lambda: rules.test_enums_and_label_rules(rows),
              lambda: rules.test_extraction_fields(rows, releases),
              lambda: rules.test_completeness_follows_rubric(rows),
              lambda: rules.test_linked_issues_exist_and_are_consistent(rows, issues),
              lambda: rules.test_tag_consistency(rows)]
    for check in checks:
        try:
            check()
        except AssertionError as e:
            problems.append(str(e).splitlines()[0])
    for r in rows:
        if set(r) != {"id", "text", "hard", "tags", "expected"} or not set(r["tags"]) <= rules.TAGS:
            problems.append(f"{r.get('id')}: row shape or unknown tag")
    return problems


def main() -> int:
    rows = load(Path(sys.argv[1]))
    problems = validate(rows)
    print("OK" if not problems else "\n".join(problems), f"({len(rows)} cases)")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
