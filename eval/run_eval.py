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
from openpyxl.chart import BarChart, Reference

from app.config import MODEL_COMPARE, MODEL_DEFAULT, ROOT, llm_backend
from app.llm import LLMError
from app.pipeline import BASELINE, PipelineConfig, analyze
from eval import grade

EVAL_DIR = ROOT / "eval"
DATASET = EVAL_DIR / "dataset_v1.jsonl"
DATASET_V2 = EVAL_DIR / "dataset_v2.jsonl"  # v1 + 20 hard classification cases (E-101..E-120)
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


def load_dataset(only_hard: bool = False, limit: int | None = None, dataset: str = "v1") -> list[dict]:
    path = {"v2": DATASET_V2, "v3": DATASET_V2.with_name("dataset_v3.jsonl"),
            "holdout": DATASET_V2.with_name("dataset_holdout.jsonl"),
            "holdout2": DATASET_V2.with_name("dataset_holdout2.jsonl")}.get(dataset, DATASET)
    cases = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    cases.sort(key=lambda c: c["id"])
    if only_hard:
        cases = [c for c in cases if c.get("hard")]
    return cases[:limit] if limit else cases


def stop_if_near_limit(run_id: str, limit: float = 0.95) -> None:
    """Headless runs use the account's Claude limits, which the user also works with: one tiny call
    reads the current use, and a run is not started above `limit`."""
    if llm_backend() == "api":
        return
    from app import headless
    headless.run(system=[{"type": "text", "text": "ok"}], messages=[{"role": "user", "content": "ok"}], schema=None,
                 tools=None, tool_runner=None, model=MODEL_DEFAULT, effort="low", max_tokens=200)
    info = headless.last_rate_limit
    used = float(info.get("utilization") or 0)
    if info.get("status") == "rejected" or used >= limit:
        raise SystemExit(f"Claude 사용 한도 {used:.0%}: {run_id} not started")


def describe(cfg: PipelineConfig) -> str:
    def on(b: bool) -> str:
        return "on" if b else "off"
    return (f"few_shot={on(cfg.few_shot)} rubric={on(cfg.rubric)} "
            f"context_select={on(cfg.context_select)} effort={cfg.effort}"
            + ("" if llm_backend() == "api" else " backend=headless")
            + ("" if cfg.cot else " cot=off") + ("" if cfg.chain else " chain=off"))


def _run_case(case: dict, cfg: PipelineConfig) -> dict:
    try:
        result, logs = analyze(case["text"], cfg)
    except Exception as e:  # LLMError or an unexpected bug: never lose the whole (paid) run
        paid = getattr(e, "partial_logs", [])  # steps that already cost money before the failure
        return {"case": case, "result": None, "error": str(e) or type(e).__name__,
                "error_type": type(e).__name__, "latency_s": sum(s.latency_s for s in paid),
                "cost_usd": sum(s.cost_usd for s in paid),
                "cache_read": sum(s.usage.cache_read or 0 for s in paid)}
    return {"case": case, "result": result, "error": "", "error_type": "",
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
        "error_type": r["error_type"],
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


TEXT_COLUMNS = {"날짜", "Run ID", "모델", "설정", "변경사항"}


def _xl_value(col: str, v: str):
    """Numeric columns go into Excel as numbers (sortable/chartable); empty stays empty."""
    if col in TEXT_COLUMNS or v == "":
        return v
    try:
        return int(v)
    except ValueError:
        try:
            return float(v)
        except ValueError:
            return v


# Per-task sheets: (metric columns, primary metric for the chart and the "vs previous run" column)
TASK_SHEETS: dict[str, tuple[list[str], str]] = {
    "분류": (["분류 정확도", "분류 macro-F1", "labels 정확도"], "분류 정확도"),
    "추출": (["추출 평균 정확도", "추출 환각률", "추출 누락률", "symptom 유무 일치", "expected 유무 일치",
             "actual 유무 일치", "repro_steps 유무 일치"], "추출 평균 정확도"),
    "스코어링": (["완성도 MAE", "우선순위 exact", "우선순위 ±1"], "우선순위 exact"),
    "이슈 연결": (["링크 정확도"], "링크 정확도"),
    "속도·비용": (["평균 응답시간(s)", "총비용(USD)", "캐시 적중 토큰"], "총비용(USD)"),
}


def _in_report(run_id: str) -> bool:
    """Smoke runs (e.g. Run-00-smoke, 3 cases) stay in runs.csv but not in the Excel report."""
    return not run_id.endswith("-smoke")


_REPEAT = re.compile(r"^(?P<base>.+)-r\d+$")


def _is_main_series(run_id: str) -> bool:
    """The one-variable experiment series on dataset_v1: no repeats (Run-07-r2) and no V2- runs."""
    return not _REPEAT.match(run_id) and not run_id.startswith(("V2-", "V3-", "HO-"))


def _repeat_sheet(wb, runs: list[dict]) -> None:
    """Mean / min / max / std of each metric over a run and its repeats (Run-07, Run-07-r2, Run-07-r3)."""
    groups: dict[str, list[dict]] = {}
    for r in runs:
        m = _REPEAT.match(r["Run ID"])
        base = m.group("base") if m else r["Run ID"]
        groups.setdefault(base, []).append(r)
    groups = {b: g for b, g in groups.items() if len(g) > 1}
    if not groups:
        return
    ws = wb.create_sheet("반복 실행")
    metrics = [c for c in RUNS_COLUMNS if c not in TEXT_COLUMNS and c not in ("데이터 건수", "오류 건수")]
    ws.append(["설정", "지표", "실행 횟수", "평균", "최소", "최대", "표준편차", "각 실행 값"])
    for base, group in groups.items():
        for m in metrics:
            vals = [v for v in (_xl_value(m, r.get(m, "")) for r in group) if isinstance(v, (int, float))]
            if not vals:
                continue
            mean = sum(vals) / len(vals)
            std = (sum((v - mean) ** 2 for v in vals) / (len(vals) - 1)) ** 0.5 if len(vals) > 1 else 0.0
            ws.append([base, m, len(vals), round(mean, 4), min(vals), max(vals), round(std, 4),
                       " / ".join(str(v) for v in vals)])
    ws.freeze_panes = "C2"


def _v2_sheet(wb, runs: list[dict], prefix: str = "V2-", title: str = "dataset_v2") -> None:
    v2 = [r for r in runs if r["Run ID"].startswith(prefix)]
    if not v2:
        return
    ws = wb.create_sheet(title)
    ws.append(RUNS_COLUMNS)
    for r in v2:
        ws.append([_xl_value(c, r.get(c, "")) for c in RUNS_COLUMNS])
    ws.freeze_panes = "C2"


def _feature_sheet(wb) -> None:
    """Features added after the main series (eval/feature_evals.py): summary rows, then each run's cases."""
    path = RESULTS_DIR.parent / "feature_evals.csv"
    if not path.exists():
        return
    rows = _read_csv(path)
    ws = wb.create_sheet("추가 기능 평가")
    if not rows:
        return
    ws.append(list(rows[0]))
    for r in rows:
        ws.append([_xl_value(c, v) if c == "값" else v for c, v in r.items()])
    for r in rows:
        cases = RESULTS_DIR / f"{r['Run ID']}.csv"
        if not cases.exists():
            continue
        ws.append([])
        ws.append([f"{r['Run ID']} ({r['기능']}) 사례별 결과"])
        with open(cases, encoding="utf-8-sig", newline="") as f:
            for row in csv.reader(f):
                ws.append(row)
    ws.freeze_panes = "C2"


def _task_sheet(wb, title: str, metrics: list[str], primary: str, runs: list[dict]) -> None:
    ws = wb.create_sheet(title)
    # compare with the previous run of the SAME model (a Sonnet comparison run must not become the
    # baseline of the next Haiku improvement)
    ws.append(["Run ID", "모델", *metrics, f"{primary} 같은 모델 이전 Run 대비", "변경사항"])
    prev_by_model: dict[str, float] = {}
    for r in runs:
        cur = _xl_value(primary, r.get(primary, ""))
        prev = prev_by_model.get(r["모델"])
        delta = round(cur - prev, 4) if isinstance(cur, (int, float)) and isinstance(prev, (int, float)) else ""
        ws.append([r["Run ID"], r["모델"], *[_xl_value(m, r.get(m, "")) for m in metrics], delta, r["변경사항"]])
        if isinstance(cur, (int, float)):
            prev_by_model[r["모델"]] = cur
    ws.freeze_panes = "B2"
    if runs:
        chart = BarChart()
        chart.title = f"{primary} (Run별)"
        col = 3 + metrics.index(primary)
        chart.add_data(Reference(ws, min_col=col, min_row=1, max_row=len(runs) + 1), titles_from_data=True)
        chart.set_categories(Reference(ws, min_col=1, min_row=2, max_row=len(runs) + 1))
        chart.legend = None
        ws.add_chart(chart, f"A{len(runs) + 4}")


def build_xlsx() -> None:
    """Regenerate runs.xlsx from runs.csv: all metrics, one sheet per task (분류·추출·스코어링·이슈 연결·
    속도·비용) for the main v1 series with the change history, 반복 실행 (mean/std over repeats),
    dataset_v2 runs, then each run's confusion matrix."""
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "전체 Run"
    ws.append(RUNS_COLUMNS)
    runs = [r for r in _read_csv(RUNS_CSV) if _in_report(r["Run ID"])]
    for r in runs:
        ws.append([_xl_value(c, r.get(c, "")) for c in RUNS_COLUMNS])
    ws.freeze_panes = "C2"
    main = [r for r in runs if _is_main_series(r["Run ID"])]
    for title, (metrics, primary) in TASK_SHEETS.items():
        _task_sheet(wb, title, metrics, primary, main)
    _repeat_sheet(wb, runs)
    _v2_sheet(wb, runs)
    _v2_sheet(wb, runs, "V3-", "dataset_v3 기법 실험")
    _v2_sheet(wb, runs, "HO-", "새 사례 검증(holdout)")
    _v2_sheet(wb, runs, "HO2-", "어려운 새 사례 검증(holdout2)")
    _feature_sheet(wb)
    used = set(wb.sheetnames)
    for r in runs:
        name = re.sub(r"[\[\]:*?/\\]", "_", f"혼동행렬 {r['Run ID']}")[:31]
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
                             context_select=not args.no_context_select, cot=not args.no_cot,
                             chain=not args.single_call)
    model = MODEL_ALIASES.get(args.model, args.model)
    cfg = PipelineConfig(model=model, few_shot=cfg.few_shot, rubric=cfg.rubric,
                         context_select=cfg.context_select, effort=args.effort or cfg.effort,
                         cot=cfg.cot, chain=cfg.chain)
    cases = load_dataset(args.only_hard, args.limit, args.dataset)
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
    ok_n = sum(not o["error"] for o in outs) or 1  # mean latency over successful cases only
    pres = ext["presence"]
    summary = {
        "날짜": datetime.now().strftime("%Y-%m-%d %H:%M"), "Run ID": args.run_id, "모델": model,
        "설정": describe(cfg) + ("" if args.dataset == "v1" else f" dataset={args.dataset}"), "데이터 건수": len(cases), "오류 건수": sum(bool(o["error"]) for o in outs),
        "분류 정확도": _fmt(cls["accuracy"]), "분류 macro-F1": _fmt(cls["macro_f1"]),
        "labels 정확도": _fmt(labels_acc), "추출 평균 정확도": _fmt(ext["accuracy"]),
        "추출 환각률": _fmt(ext["hallucination_rate"]), "추출 누락률": _fmt(ext["miss_rate"]),
        "symptom 유무 일치": _fmt(pres["symptom"]), "expected 유무 일치": _fmt(pres["expected"]),
        "actual 유무 일치": _fmt(pres["actual"]), "repro_steps 유무 일치": _fmt(pres["repro_steps"]),
        "완성도 MAE": _fmt(grade.completeness_mae([e["completeness"] for e in exp], [p["completeness"] for p in preds])),
        "우선순위 exact": _fmt(pri["exact"]), "우선순위 ±1": _fmt(pri["within_1"]),
        "링크 정확도": _fmt(grade.link_accuracy([e["linked_issue_id"] for e in exp], [p["link"] for p in preds])),
        "평균 응답시간(s)": _fmt(round(sum(o["latency_s"] for o in outs if not o["error"]) / ok_n, 3)),
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
            rec = {"id": o["case"]["id"], "error": o["error"], "error_type": o["error_type"], "latency_s": o["latency_s"],
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
    ap.add_argument("--no-cot", action="store_true", help="score without reasoning first")
    ap.add_argument("--single-call", action="store_true", help="one call for all four tasks (no chaining)")
    ap.add_argument("--effort", default=None)
    ap.add_argument("--change", default="")
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--only-hard", action="store_true")
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--dataset", choices=["v1", "v2", "v3", "holdout", "holdout2"], default="v1",
                    help="v1 = frozen 100 cases, v2 = v1 + 20 hard classification cases, holdout2 = harder blind cases")
    ap.add_argument("--prompts-dir", default=None, help="read the prompts from another folder (older prompt version)")
    args = ap.parse_args(argv)
    if (RESULTS_DIR.parent / ".stop").exists():  # a queue of runs stops before its next (paid) run
        raise SystemExit(f"eval/.stop exists: {args.run_id} not started")
    stop_if_near_limit(args.run_id)
    if args.prompts_dir:
        from app import prompts
        prompts.PROMPTS_DIR = Path(args.prompts_dir)
        prompts.load.cache_clear()
        if prompts.load("classify") is None:
            ap.error(f"no prompts in {args.prompts_dir}")
    summary = run(args)
    print(f"{summary['Run ID']}: 분류 {summary['분류 정확도']} / 추출 {summary['추출 평균 정확도']} / "
          f"오류 {summary['오류 건수']} / 비용 ${summary['총비용(USD)']}")
    return summary


if __name__ == "__main__":
    main()
