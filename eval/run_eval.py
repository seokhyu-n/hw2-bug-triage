"""Eval runner: dataset -> analyze() -> per-case CSV, confusion CSV, runs.csv row, runs.xlsx.

Usage: venv\\Scripts\\python.exe -m eval.run_eval --run-id Run-01 --baseline --change "설명"
"""
from __future__ import annotations

import argparse
import csv
import json
import re
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path

import openpyxl

from app.config import MODEL_COMPARE, MODEL_DEFAULT, ROOT
from app.llm import LLMError
from app.pipeline import BASELINE, PipelineConfig, analyze
from eval import grade

EVAL_DIR = ROOT / "eval"
DATASET = EVAL_DIR / "dataset_v1.jsonl"
RESULTS_DIR = EVAL_DIR / "results"
RUNS_CSV = EVAL_DIR / "runs.csv"
RUNS_XLSX = EVAL_DIR / "runs.xlsx"

ERR = "오류"
ERR_LINK = "<오류>"  # sentinel so a failed case never matches an expected link (even None)
MODEL_ALIASES = {"haiku": MODEL_DEFAULT, "sonnet": MODEL_COMPARE}

RUNS_COLUMNS = [
    "날짜", "Run ID", "모델", "설정", "데이터 건수", "오류 건수",
    "분류 정확도", "분류 macro-F1", "labels 정확도", "추출 평균 정확도", "추출 환각률", "추출 누락률",
    "symptom 유무 일치", "expected 유무 일치", "actual 유무 일치", "repro_steps 유무 일치",
    "완성도 MAE", "우선순위 exact", "우선순위 ±1", "링크 정확도",
    "평균 응답시간(s)", "총비용(USD)", "캐시 적중 토큰", "변경사항",
]


def load_dataset(only_hard: bool = False, limit: int | None = None) -> list[dict]:
    cases = [json.loads(line) for line in DATASET.read_text(encoding="utf-8").splitlines() if line.strip()]
    cases.sort(key=lambda c: c["id"])
    if only_hard:
        cases = [c for c in cases if c.get("hard")]
    return cases[:limit] if limit else cases


def describe(cfg: PipelineConfig) -> str:
    def on(b: bool) -> str:
        return "on" if b else "off"
    return (f"few_shot={on(cfg.few_shot)} rubric={on(cfg.rubric)} "
            f"context_select={on(cfg.context_select)} effort={cfg.effort}")


def _run_case(case: dict, cfg: PipelineConfig) -> dict:
    try:
        result, logs = analyze(case["text"], cfg)
    except LLMError as e:
        return {"case": case, "result": None, "error": str(e) or type(e).__name__,
                "latency_s": 0.0, "cost_usd": 0.0, "cache_read": 0}
    return {"case": case, "result": result, "error": "",
            "latency_s": sum(s.latency_s for s in logs), "cost_usd": sum(s.cost_usd for s in logs),
            "cache_read": sum(s.usage.cache_read or 0 for s in logs)}


def _mark(ok: bool, failed: bool) -> str:
    return ERR if failed else ("O" if ok else "X")


def _fmt(v) -> str:
    return "" if v is None else (f"{v:.4f}" if isinstance(v, float) else str(v))


def _case_row(r: dict) -> tuple[dict, dict]:
    """Returns (flat CSV row, predictions dict for graders)."""
    case, res = r["case"], r["result"]
    exp = case["expected"]
    failed = res is None
    p_cat = None if failed else res.classification.category
    p_labels = None if failed else sorted(res.classification.labels)
    p_ext = None if failed else res.extraction.model_dump()
    p_comp = None if failed else res.score.completeness
    p_prio = None if failed else res.score.priority
    p_link = ERR_LINK if failed else (res.link.linked_issue_id if res.link else None)
    ext_m = grade.extraction_metrics([exp["extraction"]], [p_ext])
    ext_ok = all(v["accuracy"] == 1.0 for v in ext_m["fields"].values())
    row = {
        "id": case["id"], "hard": case.get("hard", False), "text": case["text"], "error": r["error"],
        "exp_category": exp["category"], "pred_category": p_cat or "",
        "category_ok": _mark(p_cat == exp["category"], failed),
        "exp_labels": "|".join(sorted(exp["labels"])), "pred_labels": "|".join(p_labels or []),
        "labels_ok": _mark(p_labels == sorted(exp["labels"]), failed),
    }
    for f in grade.STRUCT_FIELDS:
        row[f"exp_{f}"] = exp["extraction"].get(f) or ""
        row[f"pred_{f}"] = (p_ext or {}).get(f) or ""
    row.update({
        "extraction_ok": _mark(ext_ok, failed),
        "exp_completeness": _fmt(exp["completeness"]), "pred_completeness": _fmt(p_comp),
        "exp_priority": exp["priority"], "pred_priority": p_prio or "",
        "priority_ok": _mark(p_prio == exp["priority"], failed),
        "exp_link": exp["linked_issue_id"] or "", "pred_link": "" if failed else (p_link or ""),
        "link_ok": _mark(p_link == exp["linked_issue_id"], failed),
        "latency_s": _fmt(round(r["latency_s"], 3)), "cost_usd": f"{r['cost_usd']:.6f}",
        "cache_read": r["cache_read"],
    })
    preds = {"category": p_cat or ERR, "labels": p_labels, "extraction": p_ext, "completeness": p_comp,
             "priority": p_prio, "link": p_link}
    return row, preds


def _write_csv(path: Path, header: list[str], rows: list[dict]) -> None:
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=header)
        w.writeheader()
        w.writerows(rows)


def _read_csv(path: Path) -> list[dict]:
    with open(path, encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def build_xlsx() -> None:
    """Regenerate runs.xlsx from runs.csv + each run's confusion CSV."""
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "runs"
    ws.append(RUNS_COLUMNS)
    runs = _read_csv(RUNS_CSV)
    for r in runs:
        ws.append([r.get(c, "") for c in RUNS_COLUMNS])
    ws.freeze_panes = "C2"
    used = {"runs"}
    for r in runs:
        name = re.sub(r"[\[\]:*?/\\]", "_", r["Run ID"])[:31]
        if name in used:
            continue
        used.add(name)
        sheet = wb.create_sheet(name)
        path = RESULTS_DIR / f"{r['Run ID']}_confusion.csv"
        if path.exists():
            with open(path, encoding="utf-8-sig", newline="") as f:
                for row in csv.reader(f):
                    sheet.append(row)
    wb.save(RUNS_XLSX)


def run(args: argparse.Namespace) -> dict:
    if args.baseline:
        cfg = BASELINE
    else:
        cfg = PipelineConfig(few_shot=not args.no_few_shot, rubric=not args.no_rubric,
                             context_select=not args.no_context_select)
    model = MODEL_ALIASES.get(args.model, args.model)
    cfg = PipelineConfig(model=model, few_shot=cfg.few_shot, rubric=cfg.rubric,
                         context_select=cfg.context_select, effort=args.effort or cfg.effort)
    cases = load_dataset(args.only_hard, args.limit)
    with ThreadPoolExecutor(max_workers=max(1, args.workers)) as pool:
        outs = list(pool.map(lambda c: _run_case(c, cfg), cases))  # map keeps dataset order

    pairs = [_case_row(o) for o in outs]
    rows = [p[0] for p in pairs]
    preds = [p[1] for p in pairs]
    exp = [c["expected"] for c in cases]
    cls = grade.classification_metrics([e["category"] for e in exp], [p["category"] for p in preds])
    ext = grade.extraction_metrics([e["extraction"] for e in exp], [p["extraction"] for p in preds])
    pri = grade.priority_metrics([e["priority"] for e in exp], [p["priority"] for p in preds])
    labels_acc = grade.link_accuracy([sorted(e["labels"]) for e in exp], [p["labels"] for p in preds])
    n = len(cases) or 1
    pres = ext["presence"]
    summary = {
        "날짜": datetime.now().strftime("%Y-%m-%d %H:%M"), "Run ID": args.run_id, "모델": model,
        "설정": describe(cfg), "데이터 건수": len(cases), "오류 건수": sum(bool(o["error"]) for o in outs),
        "분류 정확도": _fmt(cls["accuracy"]), "분류 macro-F1": _fmt(cls["macro_f1"]),
        "labels 정확도": _fmt(labels_acc), "추출 평균 정확도": _fmt(ext["accuracy"]),
        "추출 환각률": _fmt(ext["hallucination_rate"]), "추출 누락률": _fmt(ext["miss_rate"]),
        "symptom 유무 일치": _fmt(pres["symptom"]), "expected 유무 일치": _fmt(pres["expected"]),
        "actual 유무 일치": _fmt(pres["actual"]), "repro_steps 유무 일치": _fmt(pres["repro_steps"]),
        "완성도 MAE": _fmt(grade.completeness_mae([e["completeness"] for e in exp], [p["completeness"] for p in preds])),
        "우선순위 exact": _fmt(pri["exact"]), "우선순위 ±1": _fmt(pri["within_1"]),
        "링크 정확도": _fmt(grade.link_accuracy([e["linked_issue_id"] for e in exp], [p["link"] for p in preds])),
        "평균 응답시간(s)": _fmt(round(sum(o["latency_s"] for o in outs) / n, 3)),
        "총비용(USD)": f"{sum(o['cost_usd'] for o in outs):.6f}",
        "캐시 적중 토큰": sum(o["cache_read"] for o in outs), "변경사항": args.change,
    }

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    if rows:
        _write_csv(RESULTS_DIR / f"{args.run_id}.csv", list(rows[0]), rows)
    conf_rows = [{"expected\\predicted": e, **cls["confusion"][e]} for e in grade.LABELS]
    _write_csv(RESULTS_DIR / f"{args.run_id}_confusion.csv", ["expected\\predicted", *grade.LABELS], conf_rows)
    with open(RESULTS_DIR / f"{args.run_id}.jsonl", "w", encoding="utf-8", newline="\n") as f:
        for o in outs:
            rec = {"id": o["case"]["id"], "error": o["error"], "latency_s": o["latency_s"],
                   "cost_usd": o["cost_usd"], "prediction": o["result"].model_dump() if o["result"] else None}
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")

    prior = [r for r in (_read_csv(RUNS_CSV) if RUNS_CSV.exists() else []) if r["Run ID"] != args.run_id]
    _write_csv(RUNS_CSV, RUNS_COLUMNS, [*prior, summary])  # re-running the same Run ID replaces its row
    build_xlsx()
    return summary


def main(argv: list[str] | None = None) -> dict:
    ap = argparse.ArgumentParser(description="RunBuddy triage eval runner")
    ap.add_argument("--run-id", required=True)
    ap.add_argument("--model", default=MODEL_DEFAULT, help="haiku | sonnet | full model id")
    ap.add_argument("--baseline", action="store_true", help="few_shot/rubric/context_select all off")
    ap.add_argument("--no-few-shot", action="store_true")
    ap.add_argument("--no-rubric", action="store_true")
    ap.add_argument("--no-context-select", action="store_true")
    ap.add_argument("--effort", default=None)
    ap.add_argument("--change", default="")
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--only-hard", action="store_true")
    ap.add_argument("--workers", type=int, default=4)
    summary = run(ap.parse_args(argv))
    print(f"{summary['Run ID']}: 분류 {summary['분류 정확도']} / 추출 {summary['추출 평균 정확도']} / "
          f"오류 {summary['오류 건수']} / 비용 ${summary['총비용(USD)']}")
    return summary


if __name__ == "__main__":
    main()
