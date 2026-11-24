r"""Re-grade saved predictions after a label fix (no API calls).

    venv\Scripts\python.exe -m eval.regrade V3- HO-

Every run in runs.csv whose ID starts with a given prefix is graded again from
eval/results/<run>.jsonl against the current labels. Predictions, cost, latency, date, settings and
the change note stay as recorded; only the expected values and the metrics change.
"""
import argparse
import json
import sys

from app.schemas import TriageResult
from eval import run_eval as re_


def _saved(run_id: str) -> dict[str, dict]:
    cache = {r["id"]: int(r["cache_read"] or 0) for r in re_._read_csv(re_.RESULTS_DIR / f"{run_id}.csv")}
    out = {}
    for line in (re_.RESULTS_DIR / f"{run_id}.jsonl").read_text(encoding="utf-8").splitlines():
        rec = json.loads(line)
        out[rec["id"]] = {**rec, "cache_read": cache[rec["id"]]}
    return out


def regrade(run_id: str, old: dict) -> dict:
    saved = _saved(run_id)

    def replay(case, cfg):
        s = saved[case["id"]]
        result = TriageResult.model_validate(s["prediction"]) if s["prediction"] else None
        return {"case": case, "result": result, "error": s["error"], "error_type": s["error_type"],
                "latency_s": s["latency_s"], "cost_usd": s["cost_usd"], "cache_read": s["cache_read"]}

    dataset = old["설정"].rsplit("dataset=", 1)[1]
    args = argparse.Namespace(run_id=run_id, model=old["모델"], baseline=False, no_few_shot=False, no_rubric=False,
                              no_context_select=False, no_cot=False, single_call=False, effort=None,
                              change=old["변경사항"], limit=None, only_hard=False, workers=1, dataset=dataset)
    run_case, build = re_._run_case, re_.build_xlsx
    re_._run_case, re_.build_xlsx = replay, lambda: None
    try:
        new = re_.run(args)
    finally:
        re_._run_case, re_.build_xlsx = run_case, build
    return {**new, "날짜": old["날짜"], "설정": old["설정"]}


def main(prefixes: list[str]) -> None:
    rows = re_._read_csv(re_.RUNS_CSV)
    done = {r["Run ID"]: regrade(r["Run ID"], r) for r in rows if r["Run ID"].startswith(tuple(prefixes))}
    re_._write_csv(re_.RUNS_CSV, re_.RUNS_COLUMNS, [done.get(r["Run ID"], r) for r in rows])  # original order
    re_.build_xlsx()
    print(f"regraded {len(done)} runs")


if __name__ == "__main__":
    main(sys.argv[1:])
