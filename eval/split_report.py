r"""Per-split metrics from saved per-case results (no API calls).

    venv\Scripts\python.exe -m eval.split_report V3-Run-02 V3-Run-10 ...

dataset_v3 is split by case number (odd / even). NOT a held-out test: for the V3-Run-10/11 tuning the
classification, label and completeness errors of BOTH halves were read, and some rule wording comes
from even cases (E-016, E-206). Only priority errors and product facts were taken from odd IDs alone,
so agreement between the halves does not show generalization. That needs newly written cases.
Also prints metrics on the 130 new hard cases (E-121..E-250).
"""
import csv
import sys
from pathlib import Path

RESULTS = Path(__file__).resolve().parent / "results"


def load(run_id: str) -> list[dict]:
    with open(RESULTS / f"{run_id}.csv", encoding="utf-8-sig", newline="") as fh:
        return list(csv.DictReader(fh))


def metrics(rows: list[dict]) -> dict:
    def acc(key):  # a failed case (API error) counts as wrong, like eval/run_eval.py
        vals = ["X" if r["error"] else r[key] for r in rows if r["error"] or r.get(key) in ("O", "X")]
        return sum(v == "O" for v in vals) / len(vals) if vals else float("nan")
    errs = [abs(float(r["exp_completeness"]) - float(r["pred_completeness"])) for r in rows
            if r["exp_completeness"] not in ("", "None") and r["pred_completeness"] not in ("", "None")]
    return {"n": len(rows), "분류": acc("category_ok"), "labels": acc("labels_ok"), "우선순위": acc("priority_ok"),
            "링크": acc("link_ok"), "완성도 MAE": sum(errs) / len(errs) if errs else float("nan")}


def split(rows: list[dict]) -> dict[str, list[dict]]:
    num = lambda r: int(r["id"].split("-")[1])
    return {"전체": rows, "홀수": [r for r in rows if num(r) % 2], "짝수": [r for r in rows if not num(r) % 2],
            "새 130건": [r for r in rows if num(r) > 120]}


def report(run_ids: list[str]) -> list[dict]:
    out = []
    for rid in run_ids:
        for name, rows in split(load(rid)).items():
            out.append({"Run ID": rid, "구간": name, **metrics(rows)})
    return out


def main() -> None:
    for r in report(sys.argv[1:]):
        print(f"{r['Run ID']:<14} {r['구간']:<8} n={r['n']:<4} 분류 {r['분류']:.3f}  labels {r['labels']:.3f}  "
              f"우선순위 {r['우선순위']:.3f}  링크 {r['링크']:.3f}  MAE {r['완성도 MAE']:.3f}")


if __name__ == "__main__":
    main()
