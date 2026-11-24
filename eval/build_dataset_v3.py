r"""dataset_v3 = dataset_v2 (120, unchanged) + 130 hard cases (E-121..E-250).

    venv\Scripts\python.exe -m eval.build_dataset_v3

The new cases were drafted by Claude Code from the rubric, prompts and known issues in three
themes (classification boundaries a, known-issue links and extraction traps b, scoring boundaries
c) and checked against the dataset label rules (eval/validate_cases.py). Each part lists its
debatable labels in REVIEW; eval/review/v3_review.md collects them for a human check. Label fixes
after a run only need re-grading (the predictions are saved), not a new paid run.
"""
import importlib
from pathlib import Path

EVAL = Path(__file__).resolve().parent
PARTS = ("a", "b", "c")


def review_items() -> list[tuple[str, str, str]]:
    out = []
    for part in PARTS:
        mod = importlib.import_module(f"eval.new_cases_v3_{part}")
        out += [(part, cid, reason) for cid, reason in getattr(mod, "REVIEW", [])]
    return out


def main() -> None:
    lines = [x for x in (EVAL / "dataset_v2.jsonl").read_text(encoding="utf-8").splitlines() if x.strip()]
    for part in PARTS:
        lines += [x for x in (EVAL / f"dataset_v3_new_{part}.jsonl").read_text(encoding="utf-8").splitlines() if x.strip()]
    (EVAL / "dataset_v3.jsonl").write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
    items = review_items()
    md = ["# dataset_v3 정답 검토 목록", "",
          "새 사례 130건 중 판단이 갈릴 수 있는 정답. 사람이 확인하고 바꿀 것이 있으면 `eval/new_cases_v3_<part>.py`를 고친 뒤",
          "`python -m eval.new_cases_v3_<part>` → `python -m eval.build_dataset_v3`로 다시 만든다(저장된 예측으로 재채점 가능).", "",
          "| 사례 | 묶음 | 판단이 갈리는 이유 |", "|---|---|---|"]
    md += [f"| {cid} | {part} | {reason.replace('|', '/')} |" for part, cid, reason in items]
    review = EVAL / "review" / "v3_review.md"
    review.parent.mkdir(exist_ok=True)
    review.write_text("\n".join(md) + "\n", encoding="utf-8", newline="\n")
    print(f"dataset_v3: {len(lines)} cases, review items: {len(items)}")


if __name__ == "__main__":
    main()
