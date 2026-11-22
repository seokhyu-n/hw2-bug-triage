"""Print the label distribution of the evaluation dataset as Markdown tables.

Usage: venv\\Scripts\\python.exe eval\\check_dataset.py [path\\to\\dataset.jsonl]
"""
import json
import sys
from collections import Counter
from pathlib import Path

DEFAULT_PATH = Path(__file__).resolve().parent / "dataset_v1.jsonl"


def load(path: Path = DEFAULT_PATH) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def summarize(rows: list[dict]) -> dict:
    exp = [r["expected"] for r in rows]
    ext = [e["extraction"] for e in exp]
    return {
        "total": len(rows),
        "hard": sum(r["hard"] for r in rows),
        "category": Counter(e["category"] for e in exp),
        "labels": Counter("+".join(e["labels"]) for e in exp),
        "priority": Counter(e["priority"] for e in exp),
        "completeness": Counter(str(e["completeness"]) for e in exp),
        "linked_issue_id": Counter(str(e["linked_issue_id"]) for e in exp),
        "feature_area": Counter(str(x["feature_area"]) for x in ext),
        "android_version": Counter(str(x["android_version"]) for x in ext),
        "app_version": Counter(str(x["app_version"]) for x in ext),
        "tags": Counter(t for r in rows for t in r["tags"]),
    }


def _table(title: str, counter: Counter) -> str:
    lines = [f"### {title}", "", "| 값 | 건수 |", "|---|---|"]
    lines += [f"| {k} | {v} |" for k, v in sorted(counter.items(), key=lambda kv: (-kv[1], kv[0]))]
    return "\n".join(lines)


def render(summary: dict) -> str:
    head = f"## 평가셋 분포 (총 {summary['total']}건, hard {summary['hard']}건)"
    parts = [head] + [_table(k, v) for k, v in summary.items() if isinstance(v, Counter)]
    return "\n\n".join(parts) + "\n"


def main() -> None:
    path = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_PATH
    sys.stdout.reconfigure(encoding="utf-8")
    print(render(summarize(load(path))))


if __name__ == "__main__":
    main()
