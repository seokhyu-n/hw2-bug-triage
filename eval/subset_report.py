r"""Score a finished run on a subset of dataset_v2 (default: the 20 new hard cases E-101..E-120).

    venv\Scripts\python.exe -m eval.subset_report V2-Run-01 V2-Run-07
Prints classification / labels / priority accuracy for the subset and lists the misclassified cases.
"""
import json
import sys
from pathlib import Path

from eval import grade

EVAL = Path(__file__).resolve().parent
NEW_IDS = {f"E-{i}" for i in range(101, 121)}


def load_expected() -> dict[str, dict]:
    rows = [json.loads(x) for x in (EVAL / "dataset_v2.jsonl").read_text(encoding="utf-8").splitlines() if x.strip()]
    return {r["id"]: r for r in rows}


def report(run_id: str, ids: set[str] = NEW_IDS) -> dict:
    expected = load_expected()
    preds = {}
    for line in (EVAL / "results" / f"{run_id}.jsonl").read_text(encoding="utf-8").splitlines():
        rec = json.loads(line)
        if rec["id"] in ids:
            preds[rec["id"]] = rec["prediction"]
    order = sorted(ids)
    exp_cat = [expected[i]["expected"]["category"] for i in order]
    pred_cat = [(preds[i] or {}).get("classification", {}).get("category", "오류") for i in order]
    exp_lab = [sorted(expected[i]["expected"]["labels"]) for i in order]
    pred_lab = [sorted((preds[i] or {}).get("classification", {}).get("labels", [])) for i in order]
    exp_pri = [expected[i]["expected"]["priority"] for i in order]
    pred_pri = [(preds[i] or {}).get("score", {}).get("priority") for i in order]
    cls = grade.classification_metrics(exp_cat, pred_cat)
    wrong = [(i, e, p, expected[i]["text"][:50]) for i, e, p in zip(order, exp_cat, pred_cat) if e != p]
    return {"run": run_id, "n": len(order), "accuracy": cls["accuracy"], "macro_f1": cls["macro_f1"],
            "labels_acc": sum(a == b for a, b in zip(exp_lab, pred_lab)) / len(order),
            "priority_exact": grade.priority_metrics(exp_pri, pred_pri)["exact"],
            "confusion": cls["confusion"], "wrong": wrong}


def main(argv: list[str]) -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    for run_id in argv:
        r = report(run_id)
        print(f"{r['run']}: 새 사례 {r['n']}건 분류 정확도 {r['accuracy']:.2f}, macro-F1 {r['macro_f1']:.3f}, "
              f"labels {r['labels_acc']:.2f}, 우선순위 exact {r['priority_exact']:.2f}")
        for i, e, p, t in r["wrong"]:
            print(f"  틀림 {i}: 정답 {e} / 예측 {p} | {t}")


if __name__ == "__main__":
    main(sys.argv[1:])
