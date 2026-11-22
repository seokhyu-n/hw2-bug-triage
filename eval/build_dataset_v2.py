r"""dataset_v2 = dataset_v1 (100, unchanged) + dataset_v2_new (20 hard classification cases).

Labels of all 20 new cases and 36 v1 cases were checked by the user (eval/review/review_log.md).
    venv\Scripts\python.exe -m eval.build_dataset_v2
"""
from pathlib import Path

EVAL = Path(__file__).resolve().parent


def main() -> None:
    v1 = (EVAL / "dataset_v1.jsonl").read_text(encoding="utf-8").splitlines()
    new = (EVAL / "dataset_v2_new.jsonl").read_text(encoding="utf-8").splitlines()
    lines = [x for x in v1 + new if x.strip()]
    (EVAL / "dataset_v2.jsonl").write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
    print(f"dataset_v2: {len(lines)} cases")


if __name__ == "__main__":
    main()
